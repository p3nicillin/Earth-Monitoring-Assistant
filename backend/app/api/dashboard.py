import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import case, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models.entities import Event, Project, Severity, WatchArea
from app.schemas.api import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    session: SessionDep, user: CurrentUser, project_id: uuid.UUID | None = None
) -> DashboardSummary:
    project_filters = [Project.owner_id == user.id]
    if project_id is not None:
        project_filters.append(Project.id == project_id)
    active_projects = await session.scalar(
        select(func.count())
        .select_from(Project)
        .where(*project_filters, Project.is_archived.is_(False))
    )
    watch_areas = await session.scalar(
        select(func.count()).select_from(WatchArea).join(Project).where(*project_filters)
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
            .join(Project)
            .where(*project_filters)
        )
    ).one()
    category_rows = (
        await session.execute(
            select(Event.category, func.count())
            .join(Project)
            .where(*project_filters)
            .group_by(Event.category)
        )
    ).all()
    severity_rows = (
        await session.execute(
            select(Event.severity, func.count())
            .join(Project)
            .where(*project_filters)
            .group_by(Event.severity)
        )
    ).all()
    events_24h, critical_events, total_events, reviewed_events = event_metrics
    reviewed_percentage = (
        round((reviewed_events or 0) / total_events * 100, 1) if total_events else 0.0
    )
    return DashboardSummary(
        active_projects=active_projects or 0,
        watch_areas=watch_areas or 0,
        events_24h=events_24h or 0,
        critical_events=critical_events or 0,
        reviewed_percentage=reviewed_percentage,
        category_counts={category.value: count for category, count in category_rows},
        severity_counts={severity.value: count for severity, count in severity_rows},
    )
