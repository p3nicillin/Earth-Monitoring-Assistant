import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.acquisition import providers
from app.acquisition.models import SearchRequest
from app.acquisition.providers import PlanetaryComputerProvider
from app.analysis.raster_io import RasterReadError
from app.core.config import Settings
from app.detectors.base import DetectionResult, DetectorContext
from app.models.entities import EventCategory, Observation, Severity, WatchArea
from app.schemas.api import MonitoringRequest
from app.services import monitoring as monitoring_module
from app.services.monitoring import MonitoringService

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


# --- Detector wiring in MonitoringService._run_detectors -----------------------
#
# No test in this suite spins up a real database session (everything else mocks
# at the HTTP/provider boundary), so this follows the same convention: a minimal
# fake AsyncSession that resolves `select(Observation)` / `select(Event)` queries
# by inspecting the selected entity, rather than introducing a new DB fixture.


class _ScalarsResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def all(self) -> list[Any]:
        return self._items

    def __iter__(self) -> Any:
        return iter(self._items)


class _FakeSession:
    def __init__(
        self, *, recent_observations: list[Observation], existing_events: list[Any] | None = None
    ) -> None:
        self._recent_observations = recent_observations
        self._existing_events = existing_events or []
        self.added: list[Any] = []

    async def scalars(self, stmt: Any) -> _ScalarsResult:
        from app.models.entities import Event  # local import avoids a module-level cycle in tests

        entity = stmt.column_descriptions[0]["entity"]
        if entity is Observation:
            return _ScalarsResult(self._recent_observations)
        if entity is Event:
            created_events = [item for item in self.added if isinstance(item, Event)]
            return _ScalarsResult([*self._existing_events, *created_events])
        raise AssertionError(f"Unexpected query target: {entity}")

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _make_watch_area() -> WatchArea:
    return WatchArea(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Test Watch Area",
        geometry=POLYGON,
        categories=["environment"],
        schedule="daily",
        is_active=True,
    )


def _make_observation(*, captured_at: datetime, cloud_cover: float = 5.0) -> Observation:
    return Observation(
        id=uuid.uuid4(),
        source="sentinel-2-l2a",
        source_item_id=f"item-{captured_at.isoformat()}",
        captured_at=captured_at,
        cloud_cover=cloud_cover,
        assets={"B04": {"href": "https://x/b04.tif"}, "B08": {"href": "https://x/b08.tif"}},
        metadata_json={},
    )


def _flagged_result(observation_id: uuid.UUID) -> DetectionResult:
    return DetectionResult(
        flagged=True,
        title="Vegetation change detected",
        summary="synthetic test detection",
        event_type="vegetation_burn_change",
        category=EventCategory.environment,
        severity=Severity.high,
        confidence=0.9,
        geometry=POLYGON,
        area_sq_km=12.3,
        evidence={"before_item_id": "before-1", "after_item_id": "after-1"},
        observation_id=observation_id,
    )


class _StubDetector:
    name = "stub-detector"
    version = "1.0.0"

    def __init__(
        self, results: list[DetectionResult] | None = None, error: Exception | None = None
    ) -> None:
        self._results = results or []
        self._error = error
        self.call_count = 0

    async def detect(self, context: DetectorContext) -> list[DetectionResult]:
        self.call_count += 1
        if self._error is not None:
            raise self._error
        return self._results


def _settings() -> Settings:
    return Settings(secret_key="x" * 32)


def test_run_detectors_creates_event_for_flagged_result(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _make_watch_area()
    observation = _make_observation(captured_at=datetime(2026, 1, 10, tzinfo=UTC))
    detector = _StubDetector(results=[_flagged_result(observation.id)])
    monkeypatch.setattr(monitoring_module, "DETECTORS", [detector])
    session = _FakeSession(recent_observations=[observation])
    service = MonitoringService(session, _settings())  # type: ignore[arg-type]

    events_created = asyncio.run(service._run_detectors(area, POLYGON))

    assert events_created == 1
    assert detector.call_count == 1
    assert len(session.added) == 1
    created = session.added[0]
    assert created.project_id == area.project_id
    assert created.detector_name == "stub-detector"
    assert created.evidence["before_item_id"] == "before-1"


def test_run_detectors_ignores_unflagged_results(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _make_watch_area()
    observation = _make_observation(captured_at=datetime(2026, 1, 10, tzinfo=UTC))
    unflagged = DetectionResult(
        flagged=False,
        title="",
        summary="",
        event_type="vegetation_burn_change",
        category=EventCategory.environment,
        severity=Severity.low,
        confidence=0.0,
        geometry=POLYGON,
        area_sq_km=None,
        evidence={},
        observation_id=observation.id,
    )
    monkeypatch.setattr(monitoring_module, "DETECTORS", [_StubDetector(results=[unflagged])])
    session = _FakeSession(recent_observations=[observation])
    service = MonitoringService(session, _settings())  # type: ignore[arg-type]

    events_created = asyncio.run(service._run_detectors(area, POLYGON))

    assert events_created == 0
    assert session.added == []


def test_run_detectors_swallows_raster_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _make_watch_area()
    observation = _make_observation(captured_at=datetime(2026, 1, 10, tzinfo=UTC))
    detector = _StubDetector(error=RasterReadError("signing failed"))
    monkeypatch.setattr(monitoring_module, "DETECTORS", [detector])
    session = _FakeSession(recent_observations=[observation])
    service = MonitoringService(session, _settings())  # type: ignore[arg-type]

    events_created = asyncio.run(service._run_detectors(area, POLYGON))

    assert events_created == 0
    assert session.added == []


def test_run_detectors_returns_zero_with_no_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _make_watch_area()
    detector = _StubDetector(results=[])
    monkeypatch.setattr(monitoring_module, "DETECTORS", [detector])
    session = _FakeSession(recent_observations=[])
    service = MonitoringService(session, _settings())  # type: ignore[arg-type]

    events_created = asyncio.run(service._run_detectors(area, POLYGON))

    assert events_created == 0
    assert detector.call_count == 0  # short-circuits before invoking any detector


def test_run_detectors_is_idempotent_for_the_same_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _make_watch_area()
    observation = _make_observation(captured_at=datetime(2026, 1, 10, tzinfo=UTC))
    detector = _StubDetector(results=[_flagged_result(observation.id)])
    monkeypatch.setattr(monitoring_module, "DETECTORS", [detector])
    session = _FakeSession(recent_observations=[observation])
    service = MonitoringService(session, _settings())  # type: ignore[arg-type]

    first_run = asyncio.run(service._run_detectors(area, POLYGON))
    second_run = asyncio.run(service._run_detectors(area, POLYGON))

    assert first_run == 1
    assert second_run == 0
    assert len(session.added) == 1
