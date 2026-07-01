import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import CurrentUser, SessionDep
from app.models.entities import Event, EventCategory, Project, ReviewOutcome, Severity
from app.schemas.api import EventCollection, EventRead, EventReview, GeoJSONFeatureCollection

router = APIRouter(prefix="/events", tags=["events"])


def event_read(event: Event, geometry_json: str) -> EventRead:
    return EventRead(
        id=event.id,
        project_id=event.project_id,
        title=event.title,
        summary=event.summary,
        event_type=event.event_type,
        category=event.category,
        severity=event.severity,
        confidence=event.confidence,
        geometry=json.loads(geometry_json),
        area_sq_km=event.area_sq_km,
        detected_at=event.detected_at,
        detector_name=event.detector_name,
        detector_version=event.detector_version,
        evidence=event.evidence,
        is_reviewed=event.is_reviewed,
        review_outcome=event.review_outcome,
        reviewed_by_id=event.reviewed_by_id,
        reviewed_at=event.reviewed_at,
        review_note=event.review_note,
    )


def filters_for(
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    category: EventCategory | None,
    severity: Severity | None,
    since: datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Project.owner_id == user_id]
    if project_id:
        filters.append(Event.project_id == project_id)
    if category:
        filters.append(Event.category == category)
    if severity:
        filters.append(Event.severity == severity)
    if since:
        filters.append(Event.detected_at >= since)
    return filters


@router.get("", response_model=EventCollection)
async def list_events(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    category: EventCategory | None = None,
    severity: Severity | None = None,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventCollection:
    filters = filters_for(user.id, project_id, category, severity, since)
    total = await session.scalar(
        select(func.count()).select_from(Event).join(Project).where(*filters)
    )
    rows = (
        await session.execute(
            select(Event, ST_AsGeoJSON(Event.geometry))
            .join(Project)
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


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
async def events_geojson(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    category: EventCategory | None = None,
    severity: Severity | None = None,
    since: datetime | None = None,
) -> GeoJSONFeatureCollection:
    filters = filters_for(user.id, project_id, category, severity, since)
    rows = (
        await session.execute(
            select(Event, ST_AsGeoJSON(Event.geometry))
            .join(Project)
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


@router.patch("/{event_id}/review", response_model=EventRead)
async def review_event(
    event_id: uuid.UUID,
    payload: EventReview,
    session: SessionDep,
    user: CurrentUser,
) -> EventRead:
    row = (
        await session.execute(
            select(Event, ST_AsGeoJSON(Event.geometry))
            .join(Project)
            .where(Event.id == event_id, Project.owner_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event, geometry = row
    event.is_reviewed = True
    event.review_outcome = ReviewOutcome(payload.outcome)
    event.reviewed_by_id = user.id
    event.reviewed_at = datetime.now(UTC)
    event.review_note = payload.note
    await session.commit()
    return event_read(event, geometry)
