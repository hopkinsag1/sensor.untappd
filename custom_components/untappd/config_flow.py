"""Config flow for the Untappd integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import (
    UntappdAuthError,
    UntappdClient,
    UntappdError,
    UntappdNotFoundError,
    UntappdRateLimitError,
)
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): selector.TextSelector(),
        vol.Required(CONF_CLIENT_ID): selector.TextSelector(),
        vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): selector.TextSelector(),
        vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


async def _async_validate(
    hass: HomeAssistant, username: str, client_id: str, client_secret: str
) -> tuple[dict[str, str], str | None]:
    """Try one API call; return (errors, canonical username)."""
    # Imported lazily to avoid a circular import at module load.
    from . import async_build_user_agent  # noqa: PLC0415

    client = UntappdClient(
        async_get_clientsession(hass),
        client_id,
        client_secret,
        user_agent=await async_build_user_agent(hass),
    )
    try:
        user = await client.get_user_info(username)
    except UntappdAuthError:
        return {"base": "invalid_auth"}, None
    except UntappdNotFoundError:
        return {CONF_USERNAME: "user_not_found"}, None
    except UntappdRateLimitError:
        return {"base": "rate_limited"}, None
    except UntappdError:
        _LOGGER.exception("Unexpected error validating Untappd credentials")
        return {"base": "cannot_connect"}, None
    return {}, str(user.get("user_name") or username)


class UntappdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Untappd."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(_: ConfigEntry) -> UntappdOptionsFlow:
        """Return the options flow."""
        return UntappdOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            errors, _ = await _async_validate(
                self.hass,
                username,
                user_input[CONF_CLIENT_ID].strip(),
                user_input[CONF_CLIENT_SECRET].strip(),
            )
            if not errors:
                return self.async_create_entry(
                    title=f"Untappd ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                    },
                    options={CONF_SCAN_INTERVAL_MINUTES: DEFAULT_SCAN_INTERVAL_MINUTES},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_import(self, import_data: ConfigType) -> ConfigFlowResult:
        """Import a ``sensor: - platform: untappd`` block from configuration.yaml."""
        username = str(import_data[CONF_USERNAME]).strip()
        await self.async_set_unique_id(username.lower())
        self._abort_if_unique_id_configured()

        errors, _ = await _async_validate(
            self.hass,
            username,
            str(import_data[CONF_CLIENT_ID]),
            str(import_data[CONF_CLIENT_SECRET]),
        )
        if errors:
            reason = errors.get("base") or errors.get(CONF_USERNAME) or "unknown"
            return self.async_abort(reason=reason)

        minutes = DEFAULT_SCAN_INTERVAL_MINUTES
        if (interval := import_data.get(CONF_SCAN_INTERVAL)) is not None:
            minutes = max(
                MIN_SCAN_INTERVAL_MINUTES,
                min(MAX_SCAN_INTERVAL_MINUTES, round(interval.total_seconds() / 60)),
            )

        _LOGGER.info("Importing Untappd YAML configuration for user %s", username)
        return self.async_create_entry(
            title=f"Untappd ({username})",
            data={
                CONF_USERNAME: username,
                CONF_CLIENT_ID: str(import_data[CONF_CLIENT_ID]),
                CONF_CLIENT_SECRET: str(import_data[CONF_CLIENT_SECRET]),
            },
            options={CONF_SCAN_INTERVAL_MINUTES: minutes},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when the key is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new client id / secret."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            errors, _ = await _async_validate(
                self.hass,
                entry.data[CONF_USERNAME],
                user_input[CONF_CLIENT_ID].strip(),
                user_input[CONF_CLIENT_SECRET].strip(),
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )


class UntappdOptionsFlow(OptionsFlowWithReload):
    """Options: polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_MINUTES, default=current
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=MAX_SCAN_INTERVAL_MINUTES,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    )
                }
            ),
        )
