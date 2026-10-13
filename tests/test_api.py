"""Tests for the API client."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.untappd.api import (
    UntappdAuthError,
    UntappdClient,
    UntappdConnectionError,
    UntappdRateLimitError,
)

from .conftest import API, CLIENT_ID, CLIENT_SECRET, USERNAME, load_fixture


def _client(hass: HomeAssistant) -> UntappdClient:
    return UntappdClient(
        async_get_clientsession(hass), CLIENT_ID, CLIENT_SECRET, user_agent="test/1"
    )


async def test_sends_credentials_and_user_agent(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every call carries client_id, client_secret and a custom User-Agent."""
    aioclient_mock.get(
        f"{API}/user/info/{USERNAME}",
        json=load_fixture("user_info.json"),
        headers={"X-Ratelimit-Limit": "100", "X-Ratelimit-Remaining": "42"},
    )
    client = _client(hass)
    user = await client.get_user_info(USERNAME)
    assert user["user_name"] == USERNAME
    assert client.rate_limit == 100
    assert client.rate_limit_remaining == 42
    call = aioclient_mock.mock_calls[0]
    assert call[1].query["client_id"] == CLIENT_ID
    assert call[1].query["client_secret"] == CLIENT_SECRET
    assert call[3]["User-Agent"] == "test/1"


async def test_invalid_credentials_raise_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Untappd answers HTTP 500 + invalid_token for a bad key pair."""
    aioclient_mock.get(
        f"{API}/user/info/{USERNAME}",
        status=500,
        json=load_fixture("error_invalid_auth.json"),
    )
    with pytest.raises(UntappdAuthError):
        await _client(hass).get_user_info(USERNAME)


async def test_rate_limit_raises(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """HTTP 429 maps to the rate-limit error."""
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", status=429, text="slow down")
    with pytest.raises(UntappdRateLimitError):
        await _client(hass).get_user_info(USERNAME)


async def test_garbage_body_is_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An HTML error page becomes a connection error, not a crash."""
    aioclient_mock.get(f"{API}/user/info/{USERNAME}", status=502, text="<html>")
    with pytest.raises(UntappdConnectionError):
        await _client(hass).get_user_info(USERNAME)
