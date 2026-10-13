"""Constants for the Untappd integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "untappd"

CONF_USERNAME: Final = "username"
CONF_CLIENT_ID: Final = "id"
CONF_CLIENT_SECRET: Final = "secret"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 10
MIN_SCAN_INTERVAL_MINUTES: Final = 1
MAX_SCAN_INTERVAL_MINUTES: Final = 1440

API_BASE_URL: Final = "https://api.untappd.com/v4"
API_TIMEOUT_SECONDS: Final = 15
# Untappd keeps the 50 most recent badges; we only need the newest.
API_BADGE_LIMIT: Final = 5
API_WISHLIST_LIMIT: Final = 50

ATTRIBUTION: Final = "Information provided by Untappd"
ICON: Final = "mdi:glass-mug-variant"

# Legacy attribute names (kept identical to the original integration).
ATTR_ABV: Final = "abv"
ATTR_BEER: Final = "beer"
ATTR_BREWERY: Final = "brewery"
ATTR_SCORE: Final = "score"
ATTR_TOTAL_BADGES: Final = "total_badges"
ATTR_TOTAL_BEERS: Final = "total_beers"
ATTR_TOTAL_CREATED_BEERS: Final = "total_created_beers"
ATTR_TOTAL_CHECKINS: Final = "checkins"
ATTR_TOTAL_FOLLOWINGS: Final = "followings"
ATTR_TOTAL_FRIENDS: Final = "friends"
ATTR_TOTAL_PHOTOS: Final = "photos"
ATTR_BADGE: Final = "badge"
ATTR_LEVEL: Final = "level"
ATTR_DESCRIPTION: Final = "description"

# New attributes on the last check-in sensor.
ATTR_BEER_STYLE: Final = "beer_style"
ATTR_BEER_URL: Final = "beer_url"
ATTR_BREWERY_COUNTRY: Final = "brewery_country"
ATTR_CHECKIN_ID: Final = "checkin_id"
ATTR_CHECKIN_TIME: Final = "checkin_time"
ATTR_COMMENT: Final = "comment"
ATTR_VENUE: Final = "venue"
ATTR_VENUE_CITY: Final = "venue_city"
