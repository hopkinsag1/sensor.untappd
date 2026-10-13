"""Data update coordinator for Untappd."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    UntappdAuthError,
    UntappdClient,
    UntappdError,
    UntappdRateLimitError,
)
from .const import (
    API_BADGE_LIMIT,
    API_WISHLIST_LIMIT,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type UntappdConfigEntry = ConfigEntry[UntappdCoordinator]


def parse_untappd_datetime(value: Any) -> datetime | None:
    """Parse the RFC 2822 timestamps Untappd uses ("Fri, 04 Sep 2026 05:52:56 +0000")."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


@dataclass(slots=True)
class UntappdData:
    """Normalised snapshot of everything the sensors need."""

    user: dict[str, Any]
    stats: dict[str, Any]
    last_checkin: dict[str, Any] | None
    last_checkin_time: datetime | None
    last_badge: dict[str, Any] | None
    last_badge_time: datetime | None
    wishlist_count: int
    wishlist: dict[str, dict[str, Any]] = field(default_factory=dict)
    rate_limit: int | None = None
    rate_limit_remaining: int | None = None


class UntappdCoordinator(DataUpdateCoordinator[UntappdData]):
    """Poll Untappd for one user."""

    config_entry: UntappdConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: UntappdConfigEntry,
        client: UntappdClient,
    ) -> None:
        """Initialise the coordinator."""
        self.client = client
        self.username: str = entry.data[CONF_USERNAME]
        minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.username}",
            update_interval=timedelta(minutes=minutes),
        )

    async def _async_update_data(self) -> UntappdData:
        """Fetch user info, badges and wishlist in parallel."""
        try:
            user, badges, wishlist = await asyncio.gather(
                self.client.get_user_info(self.username),
                self.client.get_user_badges(self.username, limit=API_BADGE_LIMIT),
                self.client.get_user_wishlist(self.username, limit=API_WISHLIST_LIMIT),
            )
        except UntappdAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UntappdRateLimitError as err:
            # Back off for the rest of the hour-ish window rather than hammering.
            raise UpdateFailed(f"Rate limited by Untappd: {err}") from err
        except UntappdError as err:
            raise UpdateFailed(str(err)) from err

        checkins = (user.get("checkins") or {}).get("items") or []
        last_checkin = checkins[0] if checkins else None
        last_badge = badges[0] if badges else None

        wishlist_items: dict[str, dict[str, Any]] = {}
        for item in wishlist.get("items") or []:
            beer = item.get("beer") or {}
            brewery = item.get("brewery") or {}
            name = beer.get("beer_name")
            if not name:
                continue
            wishlist_items[name] = {
                "beer_name": name,
                "beer_label": beer.get("beer_label"),
                "beer_description": beer.get("beer_description"),
                "beer_abv": beer.get("beer_abv"),
                "beer_style": beer.get("beer_style"),
                "beer_ibu": beer.get("beer_ibu"),
                "beer_link": f"https://untappd.com/b/{beer.get('beer_slug')}/{beer.get('bid')}",
                "rating_score": beer.get("rating_score"),
                "rating_count": beer.get("rating_count"),
                "brewery_label": brewery.get("brewery_label"),
                "brewery_name": brewery.get("brewery_name"),
                "country_name": brewery.get("country_name"),
            }

        return UntappdData(
            user=user,
            stats=user.get("stats") or {},
            last_checkin=last_checkin,
            last_checkin_time=parse_untappd_datetime(
                last_checkin.get("created_at") if last_checkin else None
            ),
            last_badge=last_badge,
            last_badge_time=parse_untappd_datetime(
                (last_badge.get("earned_at") or last_badge.get("created_at"))
                if last_badge
                else None
            ),
            wishlist_count=int(wishlist.get("count") or 0),
            wishlist=wishlist_items,
            rate_limit=self.client.rate_limit,
            rate_limit_remaining=self.client.rate_limit_remaining,
        )
