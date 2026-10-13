"""The Untappd integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import UntappdClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN
from .coordinator import UntappdConfigEntry, UntappdCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

# YAML is only accepted on the sensor platform (for import); nothing under
# a top-level ``untappd:`` key.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (nothing to do; everything is per entry)."""
    return True


async def async_build_user_agent(hass: HomeAssistant) -> str:
    """Build the User-Agent Untappd asks every client to send."""
    integration = await async_get_integration(hass, DOMAIN)
    return (
        f"HomeAssistant-Untappd/{integration.version} "
        f"(+https://github.com/hopkinsag1/sensor.untappd)"
    )


async def async_setup_entry(hass: HomeAssistant, entry: UntappdConfigEntry) -> bool:
    """Set up Untappd from a config entry."""
    client = UntappdClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        user_agent=await async_build_user_agent(hass),
    )
    coordinator = UntappdCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UntappdConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
