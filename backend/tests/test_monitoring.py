import asyncio
import uuid

from app.models.entities import EventCategory, Severity, WatchArea
from app.services.monitoring import DemoChangeDetector, DemoImageryProvider

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-1.0, 51.0], [0.0, 51.0], [0.0, 52.0], [-1.0, 52.0], [-1.0, 51.0]]],
}


def test_demo_provider_preserves_source_geometry() -> None:
    items = asyncio.run(DemoImageryProvider().search(POLYGON, max_cloud_cover=5))
    assert len(items) == 1
    assert items[0].footprint == POLYGON
    assert items[0].cloud_cover == 5
    assert items[0].source == "demo-sentinel-2"


def test_demo_detector_is_deterministic_and_labelled() -> None:
    item = asyncio.run(DemoImageryProvider().search(POLYGON, max_cloud_cover=30))[0]
    area = WatchArea(
        id=uuid.UUID("7e94c166-b673-4022-a9b3-a43652cf271e"),
        project_id=uuid.uuid4(),
        name="Test area",
        geometry=None,
        categories=[EventCategory.disaster.value],
        schedule="manual",
    )
    detector = DemoChangeDetector()
    first = detector.detect(item, area, POLYGON)
    second = detector.detect(item, area, POLYGON)
    assert first == second
    assert first.event_type == "flood_extent"
    assert first.severity in (Severity.medium, Severity.high)
    assert first.evidence["mode"] == "demo"
    assert first.evidence["requires_human_review"] is True
