"""Shared bounded fetch-and-cache helper for public live data feeds.

Every upstream request is retried with exponential backoff and cached in
process memory for a feed-specific TTL so that dashboards and streams can
poll aggressively without hammering the public services.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings

USER_AGENT = "TerraLens/0.1 solar-system operations (open data monitor)"


class FeedError(RuntimeError):
    """A bounded upstream live-feed failure."""


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    expires_monotonic: float


_cache: dict[str, _CacheEntry] = {}
_locks: dict[str, asyncio.Lock] = {}


def clear_feed_cache() -> None:
    """Reset cached payloads and locks; intended for tests."""
    _cache.clear()
    _locks.clear()


async def fetch_json_cached(settings: Settings, url: str, ttl_seconds: float) -> Any:
    """Return the JSON payload for `url`, serving from cache while fresh."""
    entry = _cache.get(url)
    if entry is not None and entry.expires_monotonic > time.monotonic():
        return entry.value
    lock = _locks.setdefault(url, asyncio.Lock())
    async with lock:
        entry = _cache.get(url)
        if entry is not None and entry.expires_monotonic > time.monotonic():
            return entry.value
        payload = await _fetch_json(settings, url)
        _cache[url] = _CacheEntry(payload, time.monotonic() + ttl_seconds)
        return payload


async def _fetch_json(settings: Settings, url: str) -> Any:
    for attempt in range(1, settings.provider_max_attempts + 1):
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            if attempt == settings.provider_max_attempts:
                raise FeedError(f"Upstream live feed failed: {url}") from exc
            await asyncio.sleep(settings.provider_backoff_seconds * (2 ** (attempt - 1)))
    raise FeedError(f"Upstream live feed failed: {url}")
