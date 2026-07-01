import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.acquisition import providers
from app.acquisition.models import SearchRequest
from app.acquisition.providers import PlanetaryComputerProvider
from app.schemas.api import MonitoringRequest

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-1.0, 51.0], [0.0, 51.0], [0.0, 52.0], [-1.0, 52.0], [-1.0, 51.0]]],
}


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "features": [
                {
                    "id": "S2-live-item",
                    "collection": "sentinel-2-l2a",
                    "geometry": POLYGON,
                    "properties": {
                        "datetime": "2026-06-30T10:00:00Z",
                        "eo:cloud_cover": 7.5,
                        "platform": "sentinel-2a",
                        "constellation": "sentinel-2",
                    },
                    "assets": {
                        "visual": {"href": "https://example.test/visual.tif"},
                        "unsafe": {"href": "file:///restricted.tif"},
                    },
                    "links": [{"rel": "self", "href": "https://example.test/item.json"}],
                },
                {"id": "corrupt-item", "properties": {}},
            ]
        }


class FakeClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any]) -> FakeResponse:
        assert url.endswith("/search")
        assert json["collections"] == ["sentinel-2-l2a"]
        assert json["intersects"] == POLYGON
        assert json["limit"] == 20
        return FakeResponse()


class FlakyClient(FakeClient):
    attempts = 0

    async def post(self, url: str, *, json: dict[str, Any]) -> FakeResponse:
        del json
        self.__class__.attempts += 1
        if self.__class__.attempts < 3:
            raise httpx.ConnectError("temporary outage", request=httpx.Request("POST", url))
        return FakeResponse()


def test_planetary_computer_provider_validates_and_preserves_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    provider = PlanetaryComputerProvider(
        api_url="https://example.test/stac",
        collection="sentinel-2-l2a",
        timeout_seconds=20,
        max_attempts=3,
        backoff_seconds=0,
    )
    end = datetime(2026, 7, 1, tzinfo=UTC)
    request = SearchRequest(
        geometry=POLYGON,
        start=end - timedelta(days=30),
        end=end,
        max_cloud_cover=30,
        limit=20,
    )
    items = asyncio.run(provider.search(request))
    assert len(items) == 1
    assert items[0].item_id == "S2-live-item"
    assert items[0].source == "sentinel-2-l2a"
    assert items[0].cloud_cover == 7.5
    assert items[0].metadata["stac_item_url"] == "https://example.test/item.json"
    assert "visual" in items[0].assets
    assert "unsafe" not in items[0].assets
    assert len(items[0].provenance_checksum) == 64
    assert items[0].provenance_checksum == items[0].provenance_checksum


def test_search_request_rejects_invalid_geometry_and_time() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="Polygon"):
        SearchRequest(
            geometry={"type": "Point", "coordinates": [0, 0]},
            start=now - timedelta(days=1),
            end=now,
            max_cloud_cover=20,
            limit=5,
        )
    with pytest.raises(ValidationError, match="later"):
        SearchRequest(
            geometry=POLYGON,
            start=now,
            end=now,
            max_cloud_cover=20,
            limit=5,
        )


def test_provider_retries_transient_network_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    FlakyClient.attempts = 0
    monkeypatch.setattr(providers.httpx, "AsyncClient", FlakyClient)
    provider = PlanetaryComputerProvider(
        api_url="https://example.test/stac",
        collection="sentinel-2-l2a",
        timeout_seconds=20,
        max_attempts=3,
        backoff_seconds=0,
    )
    end = datetime(2026, 7, 1, tzinfo=UTC)
    items = asyncio.run(
        provider.search(
            SearchRequest(
                geometry=POLYGON,
                start=end - timedelta(days=1),
                end=end,
                max_cloud_cover=30,
                limit=20,
            )
        )
    )
    assert len(items) == 1
    assert FlakyClient.attempts == 3


def test_monitoring_request_only_accepts_live_provider() -> None:
    request = MonitoringRequest(watch_area_id="7e94c166-b673-4022-a9b3-a43652cf271e")
    assert request.provider == "planetary-computer"
    with pytest.raises(ValidationError):
        MonitoringRequest(
            watch_area_id="7e94c166-b673-4022-a9b3-a43652cf271e",
            provider="unsupported",  # type: ignore[arg-type]
        )
