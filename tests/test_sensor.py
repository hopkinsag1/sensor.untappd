"""Tests for the sensors, with emphasis on legacy compatibility."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.untappd.const import DOMAIN
from custom_components.untappd.sensor import relative_day_label

from .conftest import API, USERNAME, load_fixture

# The fixture's newest check-in is Fri, 04 Sep 2026 05:52:56 +0000.
FROZEN_NOW = "2026-10-13 18:21:00+00:00"


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(FROZEN_NOW)


async def test_legacy_entities_keep_ids_and_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Entity IDs, names, state format and attribute keys match the original."""
    checkin = hass.states.get(f"sensor.untappd_last_check_in_{USERNAME}")
    assert checkin is not None
    assert checkin.name == f"Untappd Last Check-in ({USERNAME})"
    assert checkin.state == "39 days ago"
    attrs = checkin.attributes
    # Original attribute set, same keys and same value formatting.
    assert attrs["abv"] == "5%"
    assert attrs["beer"] == "Lucky Cat"
    assert attrs["brewery"] == "Kizakura Co."
    assert attrs["score"] == "3"
    assert attrs["total_badges"] == 691
    assert attrs["total_beers"] == 430
    assert attrs["checkins"] == 472
    assert attrs["total_created_beers"] == 0
    assert attrs["friends"] == 32
    assert attrs["followings"] == 4
    assert attrs["photos"] == 169
    assert attrs["attribution"] == "Information provided by Untappd"
    assert attrs["icon"] == "mdi:glass-mug-variant"
    assert attrs["entity_picture"].startswith("https://assets.untappd.com/site/beer_logos/")
    # New details.
    assert attrs["venue"] == "Star Noodle"
    assert attrs["venue_city"] == "Lahaina"
    assert attrs["beer_style"] == "Wheat Beer - Fruited"
    assert attrs["beer_url"] == "https://untappd.com/b/kizakura-co-lucky-cat/2100736"
    assert attrs["checkin_id"] == 1598853656
    assert attrs["checkin_time"] == "2026-09-04T05:52:56+00:00"
    assert attrs["comment"] is None

    badge = hass.states.get(f"sensor.untappd_last_badge_{USERNAME}")
    assert badge is not None
    assert badge.name == f"Untappd Last Badge ({USERNAME})"
    assert badge.state == "160 days ago"
    assert badge.attributes["badge"] == "Beer Gear Summer Giveaway"
    assert badge.attributes["level"] == 1
    assert badge.attributes["description"].startswith("Chill Out.")
    assert badge.attributes["entity_picture"].endswith("BeerGear-Summer-2026-Badge_sm.jpg") or (
        "BeerGear-Summer-2026-Badge" in badge.attributes["entity_picture"]
    )

    wishlist = hass.states.get(f"sensor.untappd_wishlist_{USERNAME}")
    assert wishlist is not None
    assert wishlist.name == f"Untappd Wishlist ({USERNAME})"
    assert wishlist.state == "1"
    beer = wishlist.attributes["Lucky Cat"]
    assert beer["beer_name"] == "Lucky Cat"
    assert beer["beer_link"] == "https://untappd.com/b/kizakura-co-lucky-cat/2100736"
    assert beer["brewery_name"] == "Kizakura Co."
    assert beer["country_name"] == "Japan"
    assert beer["beer_ibu"] == 22


async def test_new_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """New sensors live under one device and use modern naming."""
    ts = hass.states.get(f"sensor.untappd_{USERNAME}_last_check_in")
    assert ts is not None
    assert ts.state == "2026-09-04T05:52:56+00:00"
    assert ts.attributes["device_class"] == "timestamp"

    badge_ts = hass.states.get(f"sensor.untappd_{USERNAME}_last_badge")
    assert badge_ts is not None
    assert badge_ts.state == "2026-05-06T21:00:36+00:00"

    assert hass.states.get(f"sensor.untappd_{USERNAME}_unique_beers").state == "430"
    assert hass.states.get(f"sensor.untappd_{USERNAME}_check_ins").state == "472"
    assert hass.states.get(f"sensor.untappd_{USERNAME}_badges").state == "691"
    assert hass.states.get(f"sensor.untappd_{USERNAME}_api_calls_remaining").state == "73"

    # Disabled-by-default extras are registered but not created.
    friends = entity_registry.async_get(f"sensor.untappd_{USERNAME}_friends")
    assert friends is not None and friends.disabled
    assert hass.states.get(f"sensor.untappd_{USERNAME}_friends") is None

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, init_integration.entry_id), init_integration.entry_id
    )
    assert device is not None
    assert device.name == f"Untappd {USERNAME}"
    assert device.configuration_url == f"http://untappd.com/user/{USERNAME}"


async def test_empty_wishlist_and_missing_venue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """An empty wishlist gives 0 and a venue-less check-in gives None attributes."""
    info = load_fixture("user_info.json")
    info["response"]["user"]["checkins"]["items"][0]["venue"] = []  # Untappd's "no venue"
    info["response"]["user"]["checkins"]["items"][0]["checkin_comment"] = "Cheers"
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", json=info)
    aioclient_mock.get(f"{API}/user/badges/{USERNAME}", json=load_fixture("user_badges.json"))
    aioclient_mock.get(
        f"{API}/user/wishlist/{USERNAME}", json=load_fixture("user_wishlist_empty.json")
    )
    await hass.config.async_set_time_zone("UTC")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    wishlist = hass.states.get(f"sensor.untappd_wishlist_{USERNAME}")
    assert wishlist.state == "0"
    assert set(wishlist.attributes) == {"attribution", "friendly_name", "icon"}

    checkin = hass.states.get(f"sensor.untappd_last_check_in_{USERNAME}")
    assert checkin.attributes["venue"] is None
    assert checkin.attributes["venue_city"] is None
    assert checkin.attributes["comment"] == "Cheers"


async def test_update_failure_marks_unavailable_then_recovers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed poll makes entities unavailable; the next good poll restores them."""
    entity_id = f"sensor.untappd_last_check_in_{USERNAME}"
    assert hass.states.get(entity_id).state == "39 days ago"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", status=503, text="down")
    aioclient_mock.get(f"{API}/user/badges/{USERNAME}", status=503, text="down")
    aioclient_mock.get(f"{API}/user/wishlist/{USERNAME}", status=503, text="down")
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", json=load_fixture("user_info.json"))
    aioclient_mock.get(f"{API}/user/badges/{USERNAME}", json=load_fixture("user_badges.json"))
    aioclient_mock.get(f"{API}/user/wishlist/{USERNAME}", json=load_fixture("user_wishlist.json"))
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id).state == "39 days ago"


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A revoked key triggers the reauth flow instead of silent failure."""
    aioclient_mock.clear_requests()
    for ep in ("info", "badges", "wishlist"):
        aioclient_mock.get(
            f"{API}/user/{ep}/{USERNAME}",
            status=500,
            json=load_fixture("error_invalid_auth.json"),
        )
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert init_integration.runtime_data.last_update_success is False
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"


async def test_unload(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(f"sensor.untappd_last_check_in_{USERNAME}").state == STATE_UNAVAILABLE


async def test_relative_day_label_uses_local_calendar_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Day boundaries follow the HA time zone, not UTC."""
    await hass.config.async_set_time_zone("America/New_York")
    tz = ZoneInfo("America/New_York")
    freezer.move_to(datetime(2026, 10, 13, 23, 30, tzinfo=tz))  # 03:30 UTC on the 14th
    assert relative_day_label(datetime(2026, 10, 13, 1, 0, tzinfo=tz)) == "Today"
    assert relative_day_label(datetime(2026, 10, 12, 23, 59, tzinfo=tz)) == "Yesterday"
    assert relative_day_label(datetime(2026, 10, 11, 12, 0, tzinfo=tz)) == "2 days ago"
    assert relative_day_label(None) is None
