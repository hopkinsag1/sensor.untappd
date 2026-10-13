"""Diagnostics support for Untappd."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from .coordinator import UntappdConfigEntry

TO_REDACT = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    "user_avatar",
    "user_avatar_hd",
    "first_name",
    "last_name",
    "location",
    "bio",
    "url",
    "contact",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: UntappdConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
    }
