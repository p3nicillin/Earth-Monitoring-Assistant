import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select

from app.api.common import owned_watch_area
from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.models.entities import WatchArea
from app.schemas.api import MonitoringRequest, MonitoringResult
from app.services.monitoring import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


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
        )
    except Exception as exc:
        await session.rollback()
        if payload.provider == "planetary-computer":
            raise HTTPException(status_code=502, detail="Imagery provider is unavailable") from exc
        raise
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
            "Monitoring completed; review generated evidence before acting."
            if outcome.source_items
            else "No suitable imagery was found in the search window."
        ),
    )
