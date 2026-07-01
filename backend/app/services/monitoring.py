import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.acquisition import SearchRequest, provider_for
from app.core.config import Settings
from app.models.entities import JobStatus, Observation, WatchArea
from app.utils.geo import shape_to_spatial


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
        await self.session.commit()
        return MonitoringOutcome(
            run_id=uuid.uuid4(),
            source_items=len(items),
            observations_created=observations_created,
            events_created=0,
        )
