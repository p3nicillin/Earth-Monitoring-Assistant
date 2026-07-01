import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select

from app.acquisition import ProviderError
from app.api.common import owned_watch_area
from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.models.entities import Observation, Project, WatchArea
from app.schemas.api import MonitoringRequest, MonitoringResult, ObservationRead
from app.services.monitoring import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/observations", response_model=list[ObservationRead])
async def list_observations(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ObservationRead]:
    query = (
        select(
            Observation,
            WatchArea.name,
            WatchArea.project_id,
            ST_AsGeoJSON(Observation.footprint),
        )
        .join(WatchArea)
        .join(Project)
        .where(Project.owner_id == user.id)
    )
    if project_id is not None:
        query = query.where(Project.id == project_id)
    rows = (
        await session.execute(query.order_by(Observation.captured_at.desc()).limit(limit))
    ).all()
    return [
        ObservationRead(
            id=observation.id,
            project_id=area_project_id,
            watch_area_id=observation.watch_area_id,
            watch_area_name=area_name,
            source=observation.source,
            source_item_id=observation.source_item_id,
            captured_at=observation.captured_at,
            cloud_cover=observation.cloud_cover,
            footprint=json.loads(footprint),
            assets=observation.assets,
            metadata=observation.metadata_json,
            provenance_checksum=observation.metadata_json.get("provenance_checksum"),
            status=observation.status.value,
            created_at=observation.created_at,
        )
        for observation, area_name, area_project_id, footprint in rows
    ]


@router.post("/runs", response_model=MonitoringResult)
async def run_monitoring(
    payload: MonitoringRequest, session: SessionDep, user: CurrentUser
) -> MonitoringResult:
    area = await owned_watch_area(session, user, payload.watch_area_id)
    geometry_json = await session.scalar(
        select(ST_AsGeoJSON(WatchArea.geometry)).where(WatchArea.id == payload.watch_area_id)
    )
    if geometry_json is None:
        raise HTTPException(status_code=422, detail="Watch area geometry is unavailable")
    try:
        outcome = await MonitoringService(session, get_settings()).run(
            area,
            json.loads(geometry_json),
            provider_name=payload.provider,
            max_cloud_cover=payload.max_cloud_cover,
            lookback_days=payload.lookback_days,
            limit=payload.limit,
        )
    except ProviderError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail="Satellite catalogue is unavailable") from exc
    result_status: Literal["completed", "no_imagery"] = (
        "completed" if outcome.source_items else "no_imagery"
    )
    return MonitoringResult(
        run_id=outcome.run_id,
        source_items=outcome.source_items,
        observations_created=outcome.observations_created,
        events_created=outcome.events_created,
        status=result_status,
        message=(
            "Sentinel-2 catalogue search completed. Source observations were stored; "
            "no detections are generated without a validated detector."
            if outcome.source_items
            else "No suitable imagery was found in the search window."
        ),
    )
