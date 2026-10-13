"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
import json
import pathlib
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.untappd.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USERNAME,
    DOMAIN,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
API = "https://api.untappd.com/v4"
USERNAME = "beerfan"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
RATE_HEADERS = {"X-Ratelimit-Limit": "100", "X-Ratelimit-Remaining": "73"}


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in every test."""


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock the three endpoints with the happy-path fixtures."""
    aioclient_mock.get(
        f"{API}/user/info/{USERNAME}",
        json=load_fixture("user_info.json"),
        headers=RATE_HEADERS,
    )
    aioclient_mock.get(
        f"{API}/user/badges/{USERNAME}",
        json=load_fixture("user_badges.json"),
        headers=RATE_HEADERS,
    )
    aioclient_mock.get(
        f"{API}/user/wishlist/{USERNAME}",
        json=load_fixture("user_wishlist.json"),
        headers=RATE_HEADERS,
    )
    return aioclient_mock


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry for the test user."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Untappd ({USERNAME})",
        unique_id=USERNAME.lower(),
        data={
            CONF_USERNAME: USERNAME,
            CONF_CLIENT_ID: CLIENT_ID,
            CONF_CLIENT_SECRET: CLIENT_SECRET,
        },
        options={CONF_SCAN_INTERVAL_MINUTES: 10},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> Generator[MockConfigEntry]:
    """Set the integration up (in UTC) and yield the loaded entry."""
    await hass.config.async_set_time_zone("UTC")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    yield mock_config_entry
