"""Read-only, whole-planet monitoring surface.

Every other endpoint in this API scopes data by `Project.owner_id ==
current_user.id` -- that boundary stays intact everywhere else. This router is
a single, narrow, explicitly-documented exception: any authenticated user (never
anonymous) may read the system-owned "Global Monitoring" project's continent-scale
watch areas and events, because planetary-scale monitoring is a shared resource,
not private per-user data. No write endpoints exist here; the scheduler
(app.scheduling.monitoring_scheduler) is the only writer, running the identical
MonitoringService/detector pipeline as any other watch area.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import CurrentUser, SessionDep
from app.api.events import event_read
from app.bootstrap.global_monitoring import get_cached_global_project_id
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models.entities import Event, EventCategory, Severity, WatchArea
from app.schemas.api import DashboardSummary, EventCollection, GeoJSONFeatureCollection

router = APIRouter(prefix="/global", tags=["global monitoring"])


def _filters(
    category: EventCategory | None, severity: Severity | None, since: datetime | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Event.project_id == get_cached_global_project_id()]
    if category:
        filters.append(Event.category == category)
    if severity:
        filters.append(Event.severity == severity)
    if since:
        filters.append(Event.detected_at >= since)
    return filters


@router.get("/events", response_model=EventCollection)
async def global_events(
    session: SessionDep,
    user: CurrentUser,
    category: EventCategory | None = None,
    severity: Severity | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> EventCollection:
    del user  # authentication only; visibility is not owner-scoped for this project
    filters = _filters(category, severity, since)
    total = await session.scalar(select(func.count()).select_from(Event).where(*filters))
    rows = (
        await session.execute(
            select(Event, ST_AsGeoJSON(Event.geometry))
            .where(*filters)
            .order_by(Event.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return EventCollection(
        items=[event_read(event, geometry) for event, geometry in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/events/geojson", response_model=GeoJSONFeatureCollection)
async def global_events_geojson(
    session: SessionDep,
    user: CurrentUser,
    category: EventCategory | None = None,
    severity: Severity | None = None,
    since: datetime | None = None,
) -> GeoJSONFeatureCollection:
    del user
    filters = _filters(category, severity, since)
    rows = (
        await session.execute(
            select(Event, ST_AsGeoJSON(Event.geometry))
            .where(*filters)
            .order_by(Event.detected_at.desc())
            .limit(1000)
        )
    ).all()
    return GeoJSONFeatureCollection(
        features=[
            {
                "type": "Feature",
                "id": str(event.id),
                "geometry": json.loads(geometry),
                "properties": {
                    "title": event.title,
                    "eventType": event.event_type,
                    "category": event.category.value,
                    "severity": event.severity.value,
                    "confidence": event.confidence,
                    "detectedAt": event.detected_at.isoformat(),
                    "areaSqKm": event.area_sq_km,
                },
            }
            for event, geometry in rows
        ]
    )


async def _summary(session: AsyncSession) -> DashboardSummary:
    project_id = get_cached_global_project_id()
    watch_areas = await session.scalar(
        select(func.count()).select_from(WatchArea).where(WatchArea.project_id == project_id)
    )
    since = datetime.now(UTC) - timedelta(hours=24)
    event_metrics = (
        await session.execute(
            select(
                func.count().filter(Event.detected_at >= since),
                func.count().filter(Event.severity == Severity.critical),
                func.count(),
                func.sum(case((Event.is_reviewed.is_(True), 1), else_=0)),
            )
            .select_from(Event)
            .where(Event.project_id == project_id)
        )
    ).one()
    category_rows = (
        await session.execute(
            select(Event.category, func.count())
            .where(Event.project_id == project_id)
            .group_by(Event.category)
        )
    ).all()
    severity_rows = (
        await session.execute(
            select(Event.severity, func.count())
            .where(Event.project_id == project_id)
            .group_by(Event.severity)
        )
    ).all()
    events_24h, critical_events, total_events, reviewed_events = event_metrics
    reviewed_percentage = (
        round((reviewed_events or 0) / total_events * 100, 1) if total_events else 0.0
    )
    return DashboardSummary(
        active_projects=1,
        watch_areas=watch_areas or 0,
        events_24h=events_24h or 0,
        critical_events=critical_events or 0,
        reviewed_percentage=reviewed_percentage,
        category_counts={category.value: count for category, count in category_rows},
        severity_counts={severity.value: count for severity, count in severity_rows},
    )


@router.get("/summary", response_model=DashboardSummary)
async def global_summary(session: SessionDep, user: CurrentUser) -> DashboardSummary:
    del user
    return await _summary(session)


@router.get("/stream", include_in_schema=True)
async def global_stream(user: CurrentUser) -> StreamingResponse:
    del user
    settings = get_settings()

    async def event_stream() -> AsyncIterator[str]:
        yield f"retry: {settings.global_stream_interval_seconds * 1000}\n\n"
        last_sent_max_detected_at: str | None = None
        while True:
            async with SessionFactory() as session:
                summary = await _summary(session)
                filters = _filters(None, None, None)
                latest = await session.scalar(select(func.max(Event.detected_at)).where(*filters))
            fingerprint = latest.isoformat() if latest else None
            if fingerprint != last_sent_max_detected_at:
                last_sent_max_detected_at = fingerprint
                yield f"event: summary\ndata: {summary.model_dump_json()}\n\n"
            await asyncio.sleep(settings.global_stream_interval_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
