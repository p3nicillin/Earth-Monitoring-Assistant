"""Live solar-system monitoring endpoints, primarily Earth-focused.

`/stream` is server-sent events: an authenticated client receives the full
overview on connect and refreshed snapshots at the configured interval.
All payloads come from cached upstream fetches, so many concurrent clients
do not multiply load on the public data providers.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.learning.baselines import cached_baselines
from app.schemas.solar_system import (
    DetectionFeed,
    EarthEventFeed,
    EphemerisSnapshot,
    NeoFeed,
    SolarSystemOverview,
    SpaceWeather,
)
from app.services.feeds import FeedError
from app.services.solar_system import SolarSystemService

router = APIRouter(prefix="/solar-system", tags=["solar system operations"])


def _service() -> SolarSystemService:
    return SolarSystemService(get_settings())


@router.get("/overview", response_model=SolarSystemOverview)
async def overview(user: CurrentUser) -> SolarSystemOverview:
    del user
    baselines = await cached_baselines(get_settings())
    return await _service().overview(baselines)


@router.get("/space-weather", response_model=SpaceWeather)
async def space_weather(user: CurrentUser) -> SpaceWeather:
    del user
    try:
        return await _service().space_weather()
    except FeedError as exc:
        raise HTTPException(status_code=502, detail="Space weather feed is unavailable") from exc


@router.get("/ephemeris", response_model=EphemerisSnapshot)
async def ephemeris(
    user: CurrentUser,
    at: Annotated[datetime | None, Query(description="UTC instant; defaults to now")] = None,
) -> EphemerisSnapshot:
    del user
    if at is not None and at.tzinfo is None:
        raise HTTPException(status_code=422, detail="Timestamp must be timezone-aware")
    return _service().ephemeris(at)


@router.get("/neo", response_model=NeoFeed)
async def neo(user: CurrentUser) -> NeoFeed:
    del user
    try:
        return await _service().neo_feed()
    except FeedError as exc:
        raise HTTPException(status_code=502, detail="Close-approach feed is unavailable") from exc


@router.get("/earth-events", response_model=EarthEventFeed)
async def earth_events(user: CurrentUser) -> EarthEventFeed:
    del user
    try:
        return await _service().earth_events()
    except FeedError as exc:
        raise HTTPException(status_code=502, detail="Earth events feed is unavailable") from exc


@router.get("/detections", response_model=DetectionFeed)
async def detections(user: CurrentUser) -> DetectionFeed:
    del user
    baselines = await cached_baselines(get_settings())
    snapshot = await _service().overview(baselines)
    return snapshot.detections


@router.get("/stream", include_in_schema=True)
async def stream(user: CurrentUser) -> StreamingResponse:
    del user
    settings = get_settings()
    service = SolarSystemService(settings)

    async def event_stream() -> AsyncIterator[str]:
        yield f"retry: {settings.solar_stream_interval_seconds * 1000}\n\n"
        while True:
            baselines = await cached_baselines(settings)
            snapshot = await service.overview(baselines)
            yield f"event: overview\ndata: {snapshot.model_dump_json()}\n\n"
            await asyncio.sleep(settings.solar_stream_interval_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
