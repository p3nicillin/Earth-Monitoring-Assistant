import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.common import owned_project
from app.api.deps import CurrentUser, SessionDep
from app.models.entities import Project, Report
from app.schemas.api import ReportCreate, ReportRead
from app.services.reports import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportRead])
async def list_reports(
    session: SessionDep, user: CurrentUser, project_id: uuid.UUID | None = None
) -> list[ReportRead]:
    query = select(Report).join(Project).where(Project.owner_id == user.id)
    if project_id:
        query = query.where(Report.project_id == project_id)
    reports = (await session.scalars(query.order_by(Report.created_at.desc()).limit(100))).all()
    return [ReportRead.model_validate(report) for report in reports]


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate, session: SessionDep, user: CurrentUser
) -> ReportRead:
    project = await owned_project(session, user, payload.project_id)
    report = await ReportService(session).generate(
        project=project,
        user=user,
        report_type=payload.report_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    return ReportRead.model_validate(report)
