"""Minimal async client for the Untappd v4 API.

Only the read-only endpoints this integration needs are implemented. Every
request authenticates with client_id and client_secret as query parameters,
which is the "unauthenticated" tier of the Untappd API that grandfathered
API keys still have access to.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import API_BASE_URL, API_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)


class UntappdError(Exception):
    """Base error for the Untappd client."""


class UntappdConnectionError(UntappdError):
    """Could not reach the API or it returned an unusable response."""


class UntappdAuthError(UntappdError):
    """The client id / secret pair was rejected."""


class UntappdRateLimitError(UntappdError):
    """The hourly rate limit for this key has been exhausted."""


class UntappdNotFoundError(UntappdError):
    """The requested user does not exist (or is private)."""


class UntappdClient:
    """Tiny wrapper around the handful of endpoints we poll."""

    def __init__(
        self,
        session: ClientSession,
        client_id: str,
        client_secret: str,
        *,
        user_agent: str,
    ) -> None:
        """Initialise the client with an existing aiohttp session."""
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self.rate_limit: int | None = None
        self.rate_limit_remaining: int | None = None

    async def _request(self, path: str, **params: Any) -> dict[str, Any]:
        """Perform a GET and return the ``response`` member of the envelope."""
        query = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            **{k: v for k, v in params.items() if v is not None},
        }
        url = f"{API_BASE_URL}/{path}"
        try:
            async with asyncio.timeout(API_TIMEOUT_SECONDS):
                resp = await self._session.get(url, params=query, headers=self._headers)
                self._read_rate_limit(resp)
                if resp.status == 429:
                    raise UntappdRateLimitError("Untappd hourly rate limit exceeded")
                try:
                    payload = await resp.json(content_type=None)
                except ValueError as err:
                    raise UntappdConnectionError(
                        f"Untappd returned non-JSON body (HTTP {resp.status})"
                    ) from err
        except TimeoutError as err:
            raise UntappdConnectionError("Timeout talking to Untappd") from err
        except ClientError as err:
            raise UntappdConnectionError(f"Error talking to Untappd: {err}") from err

        if not isinstance(payload, dict):
            raise UntappdConnectionError("Unexpected response shape from Untappd")

        meta = payload.get("meta") or {}
        code = meta.get("code", resp.status)
        if code == 200:
            response = payload.get("response")
            if not isinstance(response, dict):
                raise UntappdConnectionError("Untappd response envelope missing")
            return response

        error_type = str(meta.get("error_type") or "")
        detail = str(meta.get("developer_friendly") or meta.get("error_detail") or "")
        message = f"Untappd error {code} ({error_type}): {detail}"
        if error_type in ("invalid_auth", "invalid_token", "invalid_param") and (
            "client_id" in detail or "client_secret" in detail
        ):
            raise UntappdAuthError(message)
        if error_type == "invalid_auth":
            raise UntappdAuthError(message)
        if error_type == "invalid_limit" or code == 429:
            raise UntappdRateLimitError(message)
        if code == 404 or error_type == "invalid_param":
            raise UntappdNotFoundError(message)
        raise UntappdConnectionError(message)

    def _read_rate_limit(self, resp: ClientResponse) -> None:
        """Remember the rate-limit headers from the last response."""
        for header, attr in (
            ("X-Ratelimit-Limit", "rate_limit"),
            ("X-Ratelimit-Remaining", "rate_limit_remaining"),
        ):
            value = resp.headers.get(header)
            if value is None:
                continue
            try:
                setattr(self, attr, int(value))
            except ValueError:
                _LOGGER.debug("Unparseable %s header: %s", header, value)

    async def get_user_info(self, username: str) -> dict[str, Any]:
        """Return the user block, which embeds stats and recent check-ins."""
        response = await self._request(f"user/info/{username}")
        user = response.get("user")
        if not isinstance(user, dict):
            raise UntappdNotFoundError(f"No user block returned for {username}")
        return user

    async def get_user_badges(self, username: str, *, limit: int) -> list[dict[str, Any]]:
        """Return the most recently earned badges, newest first."""
        response = await self._request(f"user/badges/{username}", limit=limit)
        items = response.get("items")
        return items if isinstance(items, list) else []

    async def get_user_wishlist(self, username: str, *, limit: int) -> dict[str, Any]:
        """Return the wishlist block (``count`` plus ``items``)."""
        response = await self._request(f"user/wishlist/{username}", limit=limit)
        beers = response.get("beers")
        if not isinstance(beers, dict):
            return {"count": 0, "items": []}
        return beers
