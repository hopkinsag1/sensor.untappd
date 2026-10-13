# Untappd for Home Assistant

[![Validate](https://github.com/hopkinsag1/sensor.untappd/actions/workflows/validate.yaml/badge.svg)](https://github.com/hopkinsag1/sensor.untappd/actions/workflows/validate.yaml)
[![GitHub Release](https://img.shields.io/github/release/hopkinsag1/sensor.untappd.svg?style=flat-square)](https://github.com/hopkinsag1/sensor.untappd/releases)
[![License](https://img.shields.io/github/license/hopkinsag1/sensor.untappd.svg?style=flat-square)](LICENSE)

A maintained fork of [custom-components/sensor.untappd](https://github.com/custom-components/sensor.untappd),
which was archived in 2022. It brings the integration up to current Home Assistant
standards (config flow, async API client, data update coordinator, unique IDs,
diagnostics, HACS metadata) while keeping the original three sensors' entity IDs,
names, states and attributes unchanged so existing dashboards keep working.

> **You need an Untappd API key.** Untappd stopped issuing free keys; this
> integration is for people who still hold a grandfathered Client ID / Client Secret
> (or a paid one). It uses the `client_id` + `client_secret` tier, 100 calls per hour per key.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/hopkinsag1/sensor.untappd` with category **Integration**.
3. Search for "Untappd", download it, restart Home Assistant.

### Manual

Copy `custom_components/untappd/` into `<config>/custom_components/untappd/` and restart.

## Configuration

Settings → Devices & services → **Add integration** → Untappd. Enter the Untappd
username to follow and your Client ID and Client Secret. Several users can be
added, each as its own entry.

**Options** (gear icon on the entry): polling interval in minutes (default 10).
Each poll makes 3 API calls, so 10 minutes uses 18 of the 100 calls per hour.

### Migrating from the original integration

If you already have this in `configuration.yaml`:

```yaml
sensor:
  - platform: untappd
    username: average_joe
    id: !secret untappd_id
    secret: !secret untappd_secret
```

leave it in place for one restart. The block is imported into a config entry
automatically and a repair issue reminds you to delete the YAML afterwards. The
old `scan_interval`, if set, is carried over. The three original entities keep their
IDs, for example `sensor.untappd_last_check_in_average_joe`.

## Entities

### Original sensors (unchanged names, IDs and attributes)

| Entity | State | Attributes |
| --- | --- | --- |
| `sensor.untappd_last_check_in_<user>` | `Today`, `Yesterday` or `N days ago` | `abv`, `beer`, `brewery`, `score`, `total_badges`, `total_beers`, `checkins`, `total_created_beers`, `friends`, `followings`, `photos`, plus new: `beer_style`, `beer_url`, `brewery_country`, `checkin_id`, `checkin_time`, `comment`, `venue`, `venue_city`. Entity picture is the beer label. |
| `sensor.untappd_last_badge_<user>` | `Today`, `Yesterday` or `N days ago` | `badge`, `level`, `description`. Entity picture is the badge image. |
| `sensor.untappd_wishlist_<user>` | number of beers on the wishlist | one attribute per beer, keyed by beer name, with `beer_name`, `beer_label`, `beer_description`, `beer_abv`, `beer_style`, `beer_ibu`, `beer_link`, `rating_score`, `rating_count`, `brewery_label`, `brewery_name`, `country_name` (works with [list-card](https://github.com/custom-cards/list-card)). |

Two behaviour fixes versus the original: the icon is now `mdi:glass-mug-variant`
(the original had a doubled `mdi:mdi-` prefix and never rendered), and the
"N days ago" count uses calendar days in your Home Assistant time zone. The original
compared naive local time to naive UTC and added one, so it usually read one day high.

### New sensors

These sit under a device named `Untappd <user>` and use modern entity naming
(`sensor.untappd_<user>_<name>`).

| Name | Notes |
| --- | --- |
| Last check-in | Timestamp device class; HA shows it as relative time and it works in automations. Entity picture is the beer label. |
| Last badge | Timestamp of the most recently earned badge. |
| Unique beers, Check-ins, Badges | Numeric, with long-term statistics. |
| Friends, Photos | Disabled by default; enable from the entity settings. |
| API calls remaining | Diagnostic: Untappd's `X-Ratelimit-Remaining` after the last poll. |

If Untappd rejects the key pair, the entry asks you to re-authenticate instead of
silently going stale. Download diagnostics from the entry page for support; secrets
and personal profile fields are redacted.

## Development

```bash
python3.14 -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check . && pytest
```

Tests run against the real Home Assistant core via
`pytest-homeassistant-custom-component`, using anonymised API fixtures captured
from the live Untappd v4 API.

## Changelog

### 1.0.0

- Config flow with YAML import, reauth and an options flow for the polling interval.
- Async `aiohttp` client replaces the abandoned `pyuntappd` package (no external requirements).
- `DataUpdateCoordinator`, `unique_id` on every entity, device per user, diagnostics.
- 3 API calls per poll instead of 4 (the user/info call already embeds recent check-ins), default interval 10 minutes.
- Fixed icon and the relative-day arithmetic; added venue, comment, style, URL and time to the check-in sensor.
- New timestamp and statistics sensors.
- HACS metadata, hassfest + HACS validation in CI, test suite.

## Credits

Original integration by [@swetoast](https://github.com/swetoast) and
[@iantrich](https://github.com/iantrich); `pyuntappd` by [@ludeeus](https://github.com/ludeeus).
