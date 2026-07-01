import asyncio
import logging
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.acquisition.models import ImageryItem, SearchRequest, parse_stac_datetime
from app.core.config import Settings

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """Bounded provider failure safe to translate at the API boundary."""


class ImageryProvider(Protocol):
    name: str

    async def search(self, request: SearchRequest) -> list[ImageryItem]: ...


class StacProvider:
    """Resilient STAC adapter with validation, retry, and normalized provenance."""

    name = "stac"

    def __init__(
        self,
        *,
        api_url: str,
        collection: str,
        timeout_seconds: float,
        max_attempts: int,
        backoff_seconds: float,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.collection = collection
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    async def search(self, request: SearchRequest) -> list[ImageryItem]:
        payload = {
            "collections": [self.collection],
            "intersects": request.geometry,
            "datetime": f"{request.start.isoformat()}/{request.end.isoformat()}",
            "query": {"eo:cloud_cover": {"lte": request.max_cloud_cover}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            "limit": request.limit,
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(f"{self.api_url}/search", json=payload)
                    response.raise_for_status()
                return self._normalize_response(response.json())
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code in RETRYABLE_STATUS_CODES
                if not retryable or attempt == self.max_attempts:
                    raise ProviderError(
                        f"{self.name} returned HTTP {exc.response.status_code}"
                    ) from exc
            except (httpx.RequestError, ValueError, TypeError) as exc:
                if attempt == self.max_attempts:
                    raise ProviderError(f"{self.name} catalogue request failed") from exc
            await asyncio.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise ProviderError(f"{self.name} catalogue request failed")

    def _normalize_response(self, payload: object) -> list[ImageryItem]:
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ValueError("STAC response does not contain a feature list")
        items: list[ImageryItem] = []
        for feature in payload["features"]:
            try:
                items.append(self._normalize_feature(feature))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.warning("Discarding invalid STAC feature: %s", exc)
        if payload["features"] and not items:
            raise ValueError("STAC response contained no valid source items")
        return items

    def _normalize_feature(self, feature: object) -> ImageryItem:
        if not isinstance(feature, dict):
            raise ValueError("STAC feature must be an object")
        properties = feature["properties"]
        if not isinstance(properties, dict):
            raise ValueError("STAC properties must be an object")
        raw_assets = feature.get("assets", {})
        if not isinstance(raw_assets, dict):
            raise ValueError("STAC assets must be an object")
        assets = {str(key): value for key, value in raw_assets.items() if isinstance(value, dict)}
        links = feature.get("links", [])
        self_url = next(
            (
                link.get("href")
                for link in links
                if isinstance(link, dict)
                and link.get("rel") == "self"
                and isinstance(link.get("href"), str)
            ),
            None,
        )
        return ImageryItem(
            item_id=str(feature["id"]),
            source=str(feature.get("collection") or self.collection),
            captured_at=parse_stac_datetime(properties.get("datetime")),
            footprint=feature["geometry"],
            cloud_cover=properties.get("eo:cloud_cover"),
            assets=assets,
            metadata={
                "platform": properties.get("platform"),
                "constellation": properties.get("constellation"),
                "stac_collection": feature.get("collection"),
                "stac_item_url": self_url,
                "provider": self.name,
            },
        )


class PlanetaryComputerProvider(StacProvider):
    name = "planetary-computer"


def provider_for(name: str, settings: Settings) -> ImageryProvider:
    factories = {
        "planetary-computer": lambda: PlanetaryComputerProvider(
            api_url=settings.stac_api_url,
            collection=settings.stac_collection,
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=settings.provider_max_attempts,
            backoff_seconds=settings.provider_backoff_seconds,
        )
    }
    try:
        return factories[name]()
    except KeyError as exc:
        raise ProviderError(f"Unsupported imagery provider: {name}") from exc
