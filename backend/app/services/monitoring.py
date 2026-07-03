import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.acquisition import SearchRequest, provider_for
from app.analysis.raster_io import RasterReadError
from app.core.config import Settings
from app.detectors.base import DetectionResult, Detector, DetectorContext
from app.detectors.vegetation_change import VegetationChangeDetector
from app.models.entities import Event, JobStatus, Observation, WatchArea
from app.utils.geo import shape_to_spatial

logger = logging.getLogger(__name__)

# The one place detectors are registered. A detector runs against a watch area's
# already-persisted observations and never touches the session itself -- only
# this service turns a flagged DetectionResult into a committed Event.
DETECTORS: list[Detector] = [VegetationChangeDetector()]

# A large watch area can span dozens of Sentinel-2 tiles; the detector needs
# each tile's own recent history to find a same-tile before/after pair (see
# VegetationChangeDetector.select_pair), not just "the N most recent
# observations overall" -- which for a multi-tile area are almost never two
# of the same tile. This is an indexed, DB-local query, so a generous window
# costs nothing like an extra STAC/network call would.
_RECENT_OBSERVATIONS_WINDOW = 300


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
        lookback_days: int,
        limit: int,
    ) -> MonitoringOutcome:
        end = datetime.now(UTC)
        request = SearchRequest(
            geometry=geometry,
            start=end - timedelta(days=lookback_days),
            end=end,
            max_cloud_cover=max_cloud_cover,
            limit=min(limit, self.settings.provider_max_items),
        )
        provider = provider_for(provider_name, self.settings)
        items = await provider.search(request)
        observations_created = 0
        for item in items:
            existing = await self.session.scalar(
                select(Observation.id).where(
                    Observation.watch_area_id == area.id,
                    Observation.source == item.source,
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
                footprint=shape_to_spatial(shape(item.footprint)),
                assets=item.assets,
                metadata_json={
                    **item.metadata,
                    "provenance_checksum": item.provenance_checksum,
                    "search": {
                        "start": request.start.isoformat(),
                        "end": request.end.isoformat(),
                        "max_cloud_cover": request.max_cloud_cover,
                    },
                },
                status=JobStatus.completed,
            )
            self.session.add(observation)
            await self.session.flush()
            observations_created += 1

        area.last_checked_at = datetime.now(UTC)
        events_created = await self._run_detectors(area, geometry)
        await self.session.commit()
        return MonitoringOutcome(
            run_id=uuid.uuid4(),
            source_items=len(items),
            observations_created=observations_created,
            events_created=events_created,
        )

    async def _run_detectors(self, area: WatchArea, geometry: dict[str, Any]) -> int:
        recent = (
            await self.session.scalars(
                select(Observation)
                .where(Observation.watch_area_id == area.id)
                .order_by(Observation.captured_at.desc())
                .limit(_RECENT_OBSERVATIONS_WINDOW)
            )
        ).all()
        if not recent:
            return 0
        context = DetectorContext(
            watch_area=area, geometry=geometry, observations=list(recent), settings=self.settings
        )
        events_created = 0
        for detector in DETECTORS:
            try:
                results = await detector.detect(context)
            except RasterReadError:
                # A detector failure must never roll back the observations already
                # committed above; skip this detector for this run and move on.
                logger.warning(
                    "Detector %s failed for watch area %s", detector.name, area.id, exc_info=True
                )
                continue
            for result in results:
                if not result.flagged:
                    continue
                if await self._event_already_exists(area.project_id, detector, result):
                    continue
                self.session.add(
                    Event(
                        project_id=area.project_id,
                        observation_id=result.observation_id,
                        title=result.title,
                        summary=result.summary,
                        event_type=result.event_type,
                        category=result.category,
                        severity=result.severity,
                        confidence=result.confidence,
                        geometry=shape_to_spatial(shape(result.geometry)),
                        area_sq_km=result.area_sq_km,
                        detector_name=detector.name,
                        detector_version=detector.version,
                        evidence=result.evidence,
                    )
                )
                await self.session.flush()
                events_created += 1
        return events_created

    async def _event_already_exists(
        self, project_id: uuid.UUID, detector: Detector, result: DetectionResult
    ) -> bool:
        before_id = result.evidence.get("before_item_id")
        after_id = result.evidence.get("after_item_id")
        candidates = await self.session.scalars(
            select(Event).where(
                Event.project_id == project_id,
                Event.detector_name == detector.name,
                Event.detector_version == detector.version,
            )
        )
        return any(
            candidate.evidence.get("before_item_id") == before_id
            and candidate.evidence.get("after_item_id") == after_id
            for candidate in candidates
        )
