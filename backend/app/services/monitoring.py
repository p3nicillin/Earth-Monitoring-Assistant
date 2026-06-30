import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.entities import (
    Event,
    EventCategory,
    JobStatus,
    Observation,
    Severity,
    WatchArea,
)


@dataclass(frozen=True)
class ImageryItem:
    item_id: str
    source: str
    captured_at: datetime
    footprint: dict[str, Any]
    cloud_cover: float | None
    assets: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Detection:
    title: str
    summary: str
    event_type: str
    category: EventCategory
    severity: Severity
    confidence: float
    geometry: dict[str, Any]
    area_sq_km: float | None
    detector_name: str
    detector_version: str
    evidence: dict[str, Any]


class ImageryProvider(Protocol):
    async def search(
        self, geometry: dict[str, Any], *, max_cloud_cover: float
    ) -> list[ImageryItem]: ...


class DemoImageryProvider:
    async def search(
        self, geometry: dict[str, Any], *, max_cloud_cover: float
    ) -> list[ImageryItem]:
        now = datetime.now(UTC)
        stamp = now.strftime("%Y-%m-%d-%H")
        return [
            ImageryItem(
                item_id=f"demo-s2-{stamp}",
                source="demo-sentinel-2",
                captured_at=now - timedelta(hours=2),
                footprint=geometry,
                cloud_cover=min(8.4, max_cloud_cover),
                assets={"visual": {"href": "demo://sentinel-2/visual"}},
                metadata={"platform": "sentinel-2b", "mode": "deterministic-demo"},
            )
        ]


class PlanetaryComputerProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(
        self, geometry: dict[str, Any], *, max_cloud_cover: float
    ) -> list[ImageryItem]:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)
        payload = {
            "collections": [self.settings.stac_collection],
            "intersects": geometry,
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "query": {"eo:cloud_cover": {"lte": max_cloud_cover}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            "limit": 5,
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.stac_api_url.rstrip('/')}/search", json=payload
            )
            response.raise_for_status()
        features = response.json().get("features", [])
        return [
            ImageryItem(
                item_id=item["id"],
                source=self.settings.stac_collection,
                captured_at=datetime.fromisoformat(
                    item["properties"]["datetime"].replace("Z", "+00:00")
                ),
                footprint=item["geometry"],
                cloud_cover=item["properties"].get("eo:cloud_cover"),
                assets={
                    key: {"href": value.get("href"), "type": value.get("type")}
                    for key, value in item.get("assets", {}).items()
                },
                metadata={
                    "platform": item["properties"].get("platform"),
                    "constellation": item["properties"].get("constellation"),
                    "stac_collection": item.get("collection"),
                },
            )
            for item in features
        ]


class DemoChangeDetector:
    name = "demo-auditable-change-detector"
    version = "1.0.0"

    def detect(self, item: ImageryItem, area: WatchArea, geometry: dict[str, Any]) -> Detection:
        categories = area.categories or [EventCategory.environment.value]
        category = EventCategory(categories[0])
        event_type_by_category = {
            EventCategory.environment: "vegetation_change",
            EventCategory.agriculture: "crop_stress",
            EventCategory.urban: "new_construction",
            EventCategory.infrastructure: "infrastructure_change",
            EventCategory.disaster: "flood_extent",
            EventCategory.maritime: "vessel_activity",
        }
        digest = hashlib.sha256(f"{area.id}:{item.item_id}".encode()).digest()
        confidence = round(0.72 + digest[0] / 255 * 0.22, 3)
        event_type = event_type_by_category[category]
        severity = Severity.high if confidence >= 0.88 else Severity.medium
        return Detection(
            title=event_type.replace("_", " ").title(),
            summary=(
                f"Demonstration signal for {area.name}. Review the linked source observation "
                "before operational use."
            ),
            event_type=event_type,
            category=category,
            severity=severity,
            confidence=confidence,
            geometry=geometry,
            area_sq_km=round(1.2 + digest[1] / 255 * 16, 2),
            detector_name=self.name,
            detector_version=self.version,
            evidence={
                "mode": "demo",
                "source_item_id": item.item_id,
                "cloud_cover": item.cloud_cover,
                "requires_human_review": True,
            },
        )


@dataclass(frozen=True)
class MonitoringOutcome:
    run_id: uuid.UUID
    source_items: int
    observations_created: int
    events_created: int


class MonitoringService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def run(
        self,
        area: WatchArea,
        geometry: dict[str, Any],
        *,
        provider_name: str,
        max_cloud_cover: float,
    ) -> MonitoringOutcome:
        provider: ImageryProvider
        if provider_name == "planetary-computer":
            provider = PlanetaryComputerProvider(self.settings)
        else:
            provider = DemoImageryProvider()

        items = await provider.search(geometry, max_cloud_cover=max_cloud_cover)
        observations_created = 0
        events_created = 0
        for item in items:
            existing = await self.session.scalar(
                select(Observation.id).where(
                    Observation.watch_area_id == area.id,
                    Observation.source_item_id == item.item_id,
                )
            )
            if existing:
                continue
            observation = Observation(
                watch_area_id=area.id,
                source=item.source,
                source_item_id=item.item_id,
                captured_at=item.captured_at,
                cloud_cover=item.cloud_cover,
                footprint=from_shape(shape(item.footprint), srid=4326),
                assets=item.assets,
                metadata_json=item.metadata,
                status=JobStatus.completed,
            )
            self.session.add(observation)
            await self.session.flush()
            observations_created += 1

            # Only demo imagery produces a demo event. Real STAC acquisitions are ingested without
            # fabricating a scientific conclusion; a production detector must be explicitly added.
            if provider_name == "demo":
                detection = DemoChangeDetector().detect(item, area, geometry)
                self.session.add(
                    Event(
                        project_id=area.project_id,
                        observation_id=observation.id,
                        title=detection.title,
                        summary=detection.summary,
                        event_type=detection.event_type,
                        category=detection.category,
                        severity=detection.severity,
                        confidence=detection.confidence,
                        geometry=from_shape(shape(detection.geometry), srid=4326),
                        area_sq_km=detection.area_sq_km,
                        detector_name=detection.detector_name,
                        detector_version=detection.detector_version,
                        evidence=detection.evidence,
                    )
                )
                events_created += 1

        area.last_checked_at = datetime.now(UTC)
        await self.session.commit()
        return MonitoringOutcome(
            run_id=uuid.uuid4(),
            source_items=len(items),
            observations_created=observations_created,
            events_created=events_created,
        )
