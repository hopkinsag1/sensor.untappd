"""Sensors for the Untappd integration.

Three "legacy" sensors keep the exact entity IDs, names, states and
attributes of the original custom-components/sensor.untappd integration so
existing dashboards and automations keep working. The remaining sensors are
new and use modern entity naming under a per-user device.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import EntityCategory
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify
import voluptuous as vol

from .const import (
    ATTR_ABV,
    ATTR_BADGE,
    ATTR_BEER,
    ATTR_BEER_STYLE,
    ATTR_BEER_URL,
    ATTR_BREWERY,
    ATTR_BREWERY_COUNTRY,
    ATTR_CHECKIN_ID,
    ATTR_CHECKIN_TIME,
    ATTR_COMMENT,
    ATTR_DESCRIPTION,
    ATTR_LEVEL,
    ATTR_SCORE,
    ATTR_TOTAL_BADGES,
    ATTR_TOTAL_BEERS,
    ATTR_TOTAL_CHECKINS,
    ATTR_TOTAL_CREATED_BEERS,
    ATTR_TOTAL_FOLLOWINGS,
    ATTR_TOTAL_FRIENDS,
    ATTR_TOTAL_PHOTOS,
    ATTR_VENUE,
    ATTR_VENUE_CITY,
    ATTRIBUTION,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_USERNAME,
    DOMAIN,
    ICON,
)
from .coordinator import UntappdConfigEntry, UntappdCoordinator, UntappdData

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
    }
)

INTEGRATION_TITLE = "Untappd"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import a YAML sensor platform block into a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=config
    )
    if result.get("type") is FlowResultType.ABORT and result.get("reason") != "already_configured":
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_issue_{result.get('reason')}",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.ERROR,
            translation_key="deprecated_yaml_import_issue",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": INTEGRATION_TITLE,
                "reason": str(result.get("reason")),
                "username": str(config.get(CONF_USERNAME)),
            },
        )
        return

    ir.async_create_issue(
        hass,
        HOMEASSISTANT_DOMAIN,
        f"deprecated_yaml_{DOMAIN}",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={
            "domain": DOMAIN,
            "integration_title": INTEGRATION_TITLE,
        },
    )


def relative_day_label(moment: datetime | None) -> str | None:
    """Return Today / Yesterday / N days ago, in the HA time zone.

    The original integration compared a naive local "now" against a naive UTC
    timestamp and then added one to the day count; this version counts
    calendar days in the configured time zone.
    """
    if moment is None:
        return None
    today = dt_util.now().date()
    then = dt_util.as_local(moment).date()
    days = (today - then).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return f"{days} days ago"


def _checkin_venue(checkin: dict[str, Any]) -> dict[str, Any]:
    """Untappd returns an empty list instead of null when there is no venue."""
    venue = checkin.get("venue")
    return venue if isinstance(venue, dict) else {}


# ---------------------------------------------------------------------------
# Legacy sensors (names, entity IDs and attributes preserved)
# ---------------------------------------------------------------------------


class UntappdLegacySensor(CoordinatorEntity[UntappdCoordinator], SensorEntity):
    """Base for the three original sensors."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = False
    _attr_icon = ICON

    def __init__(self, coordinator: UntappdCoordinator, key: str, label: str) -> None:
        """Initialise with the original naming scheme."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_name = f"Untappd {label} ({coordinator.username})"
        # Pin the object id the original integration produced (slugified name)
        # so existing dashboards and automations keep resolving.
        self.entity_id = f"{SENSOR_DOMAIN}.{slugify(self._attr_name)}"
        # Deliberately not attached to the device: HA 2026 prefixes the device
        # name onto the friendly name of device-bound entities, which would
        # rename these three.

    @property
    def data(self) -> UntappdData:
        """Shortcut to the coordinator snapshot."""
        return self.coordinator.data


class UntappdLastCheckinSensor(UntappdLegacySensor):
    """Last check-in as a relative day, with beer details as attributes."""

    def __init__(self, coordinator: UntappdCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "last_checkin", "Last Check-in")

    @property
    def native_value(self) -> StateType:
        """Return Today / Yesterday / N days ago."""
        return relative_day_label(self.data.last_checkin_time)

    @property
    def entity_picture(self) -> str | None:
        """Return the beer label."""
        if not self.data.last_checkin:
            return None
        return (self.data.last_checkin.get("beer") or {}).get("beer_label")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Legacy attributes first, then the new check-in details."""
        checkin = self.data.last_checkin or {}
        beer = checkin.get("beer") or {}
        brewery = checkin.get("brewery") or {}
        venue = _checkin_venue(checkin)
        stats = self.data.stats
        abv = beer.get("beer_abv")
        attrs: dict[str, Any] = {
            ATTR_ABV: f"{abv}%" if abv is not None else None,
            ATTR_BEER: beer.get("beer_name"),
            ATTR_BREWERY: brewery.get("brewery_name"),
            ATTR_SCORE: (str(checkin["rating_score"]) if "rating_score" in checkin else None),
            ATTR_TOTAL_BADGES: stats.get("total_badges"),
            ATTR_TOTAL_BEERS: stats.get("total_beers"),
            ATTR_TOTAL_CHECKINS: stats.get("total_checkins"),
            ATTR_TOTAL_CREATED_BEERS: stats.get("total_created_beers"),
            ATTR_TOTAL_FRIENDS: stats.get("total_friends"),
            ATTR_TOTAL_FOLLOWINGS: stats.get("total_followings"),
            ATTR_TOTAL_PHOTOS: stats.get("total_photos"),
            # New in the fork:
            ATTR_BEER_STYLE: beer.get("beer_style"),
            ATTR_BEER_URL: (
                f"https://untappd.com/b/{beer['beer_slug']}/{beer['bid']}"
                if beer.get("beer_slug") and beer.get("bid")
                else None
            ),
            ATTR_BREWERY_COUNTRY: brewery.get("country_name"),
            ATTR_CHECKIN_ID: checkin.get("checkin_id"),
            ATTR_CHECKIN_TIME: (
                self.data.last_checkin_time.isoformat() if self.data.last_checkin_time else None
            ),
            ATTR_COMMENT: checkin.get("checkin_comment") or None,
            ATTR_VENUE: venue.get("venue_name"),
            ATTR_VENUE_CITY: (venue.get("location") or {}).get("venue_city"),
        }
        return attrs


class UntappdWishlistSensor(UntappdLegacySensor):
    """Wishlist count, with one attribute per wish-listed beer."""

    def __init__(self, coordinator: UntappdCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "wishlist", "Wishlist")

    @property
    def native_value(self) -> StateType:
        """Return the number of beers on the wishlist."""
        return self.data.wishlist_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the wishlist keyed by beer name, as the original did."""
        return dict(self.data.wishlist)


class UntappdLastBadgeSensor(UntappdLegacySensor):
    """Most recently earned badge as a relative day."""

    def __init__(self, coordinator: UntappdCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "last_badge", "Last Badge")

    @property
    def native_value(self) -> StateType:
        """Return Today / Yesterday / N days ago."""
        return relative_day_label(self.data.last_badge_time)

    @property
    def entity_picture(self) -> str | None:
        """Return the small badge image."""
        if not self.data.last_badge:
            return None
        return (self.data.last_badge.get("media") or {}).get("badge_image_sm")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return badge name, level and description."""
        badge = self.data.last_badge or {}
        levels = badge.get("levels")
        level = 1
        if badge.get("is_level") and isinstance(levels, dict):
            level = levels.get("count", 1)
        return {
            ATTR_BADGE: badge.get("badge_name"),
            ATTR_LEVEL: level,
            ATTR_DESCRIPTION: badge.get("badge_description"),
        }


# ---------------------------------------------------------------------------
# New sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class UntappdSensorEntityDescription(SensorEntityDescription):
    """Describe one of the new sensors."""

    value_fn: Callable[[UntappdData], StateType | datetime]
    picture_fn: Callable[[UntappdData], str | None] | None = None


def _stat(key: str) -> Callable[[UntappdData], StateType]:
    return lambda data: data.stats.get(key)


NEW_SENSORS: tuple[UntappdSensorEntityDescription, ...] = (
    UntappdSensorEntityDescription(
        key="last_checkin_time",
        translation_key="last_checkin_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_checkin_time,
        picture_fn=lambda data: (
            (data.last_checkin.get("beer") or {}).get("beer_label") if data.last_checkin else None
        ),
    ),
    UntappdSensorEntityDescription(
        key="last_badge_time",
        translation_key="last_badge_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_badge_time,
        picture_fn=lambda data: (
            (data.last_badge.get("media") or {}).get("badge_image_sm") if data.last_badge else None
        ),
    ),
    UntappdSensorEntityDescription(
        key="total_beers",
        translation_key="total_beers",
        icon="mdi:beer",
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("total_beers"),
    ),
    UntappdSensorEntityDescription(
        key="total_checkins",
        translation_key="total_checkins",
        icon="mdi:map-marker-check",
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("total_checkins"),
    ),
    UntappdSensorEntityDescription(
        key="total_badges",
        translation_key="total_badges",
        icon="mdi:medal",
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("total_badges"),
    ),
    UntappdSensorEntityDescription(
        key="total_friends",
        translation_key="total_friends",
        icon="mdi:account-group",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=_stat("total_friends"),
    ),
    UntappdSensorEntityDescription(
        key="total_photos",
        translation_key="total_photos",
        icon="mdi:camera",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=_stat("total_photos"),
    ),
    UntappdSensorEntityDescription(
        key="api_calls_remaining",
        translation_key="api_calls_remaining",
        icon="mdi:api",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.rate_limit_remaining,
    ),
)


class UntappdSensor(CoordinatorEntity[UntappdCoordinator], SensorEntity):
    """A sensor described by an entity description."""

    entity_description: UntappdSensorEntityDescription
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UntappdCoordinator,
        description: UntappdSensorEntityDescription,
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> StateType | datetime:
        """Return the described value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def entity_picture(self) -> str | None:
        """Return a picture when the description provides one."""
        if self.entity_description.picture_fn is None:
            return None
        return self.entity_description.picture_fn(self.coordinator.data)


def _device_info(coordinator: UntappdCoordinator) -> DeviceInfo:
    user = coordinator.data.user if coordinator.data else {}
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        name=f"Untappd {coordinator.username}",
        manufacturer="Untappd",
        model="User profile",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=user.get("untappd_url")
        or f"https://untappd.com/user/{coordinator.username}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UntappdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        UntappdLastCheckinSensor(coordinator),
        UntappdWishlistSensor(coordinator),
        UntappdLastBadgeSensor(coordinator),
    ]
    entities.extend(UntappdSensor(coordinator, desc) for desc in NEW_SENSORS)
    async_add_entities(entities)
