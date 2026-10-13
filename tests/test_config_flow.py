"""Tests for the config, import, reauth and options flows."""

from __future__ import annotations

from datetime import timedelta

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.untappd.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USERNAME,
    DOMAIN,
)

from .conftest import API, CLIENT_ID, CLIENT_SECRET, USERNAME, load_fixture

USER_INPUT = {
    CONF_USERNAME: USERNAME,
    CONF_CLIENT_ID: CLIENT_ID,
    CONF_CLIENT_SECRET: CLIENT_SECRET,
}


async def test_user_flow_success(hass: HomeAssistant, mock_api: AiohttpClientMocker) -> None:
    """A valid key pair creates an entry keyed on the lower-cased username."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Untappd ({USERNAME})"
    assert result["data"] == USER_INPUT
    assert result["options"] == {CONF_SCAN_INTERVAL_MINUTES: 10}
    assert result["result"].unique_id == USERNAME.lower()


async def test_user_flow_invalid_auth_then_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Bad credentials show an error; the form can be resubmitted."""
    aioclient_mock.get(
        f"{API}/user/info/{USERNAME}",
        status=500,
        json=load_fixture("error_invalid_auth.json"),
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", json=load_fixture("user_info.json"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate_aborts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """The same user (any letter case) cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**USER_INPUT, CONF_USERNAME: USERNAME.upper()}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_yaml_import_creates_entry_and_issue(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    """The legacy sensor platform block is imported once and flagged as deprecated."""
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": [
                {
                    "platform": DOMAIN,
                    CONF_USERNAME: USERNAME,
                    CONF_CLIENT_ID: CLIENT_ID,
                    CONF_CLIENT_SECRET: CLIENT_SECRET,
                    CONF_SCAN_INTERVAL: timedelta(minutes=5),
                }
            ]
        },
    )
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == config_entries.SOURCE_IMPORT
    assert entry.data == USER_INPUT
    assert entry.options == {CONF_SCAN_INTERVAL_MINUTES: 5}
    assert entry.state is config_entries.ConfigEntryState.LOADED

    # Legacy entity IDs survive the import.
    assert hass.states.get(f"sensor.untappd_last_check_in_{USERNAME}") is not None
    assert issue_registry.async_get_issue("homeassistant", f"deprecated_yaml_{DOMAIN}")


async def test_yaml_import_bad_credentials_raises_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    """A YAML block Untappd rejects gets its own repair issue instead of an entry."""
    aioclient_mock.get(
        f"{API}/user/info/{USERNAME}",
        status=500,
        json=load_fixture("error_invalid_auth.json"),
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {"sensor": [{"platform": DOMAIN, **USER_INPUT}]},
    )
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(DOMAIN) == []
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_yaml_import_issue_invalid_auth")


async def test_reauth_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Reauth swaps the key pair and reloads."""
    entry = init_integration
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CLIENT_ID: "new-id", CONF_CLIENT_SECRET: "new-secret"},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_CLIENT_ID] == "new-id"
    assert entry.data[CONF_CLIENT_SECRET] == "new-secret"
    assert entry.data[CONF_USERNAME] == USERNAME


async def test_options_flow_changes_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Changing the interval is stored and the entry reloads with it."""
    entry = init_integration
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SCAN_INTERVAL_MINUTES: 30}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL_MINUTES: 30}
    assert entry.runtime_data.update_interval == timedelta(minutes=30)
