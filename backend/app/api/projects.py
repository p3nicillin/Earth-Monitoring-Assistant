import json
import uuid

from fastapi import APIRouter, Response, status
from geoalchemy2.functions import ST_AsGeoJSON
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import func, select

from app.api.common import owned_project
from app.api.deps import CurrentUser, SessionDep
from app.models.entities import Event, Project, WatchArea
from app.schemas.api import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    WatchAreaCreate,
    WatchAreaRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def project_read(project: Project, watch_area_count: int = 0, event_count: int = 0) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        color=project.color,
        is_archived=project.is_archived,
        created_at=project.created_at,
        watch_area_count=watch_area_count,
        event_count=event_count,
    )


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: SessionDep, user: CurrentUser) -> list[ProjectRead]:
    rows = (
        await session.execute(
            select(
                Project,
                func.count(func.distinct(WatchArea.id)),
                func.count(func.distinct(Event.id)),
            )
            .outerjoin(WatchArea)
            .outerjoin(Event)
            .where(Project.owner_id == user.id)
            .group_by(Project.id)
            .order_by(Project.created_at.desc())
        )
    ).all()
    return [
        project_read(project, watch_count, event_count)
        for project, watch_count, event_count in rows
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: SessionDep, user: CurrentUser
) -> ProjectRead:
    project = Project(owner_id=user.id, **payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project_read(project)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ProjectRead:
    project = await owned_project(session, user, project_id)
    watch_count = await session.scalar(
        select(func.count()).select_from(WatchArea).where(WatchArea.project_id == project.id)
    )
    event_count = await session.scalar(
        select(func.count()).select_from(Event).where(Event.project_id == project.id)
    )
    return project_read(project, watch_count or 0, event_count or 0)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, session: SessionDep, user: CurrentUser
) -> ProjectRead:
    project = await owned_project(session, user, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project_read(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    project = await owned_project(session, user, project_id)
    await session.delete(project)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/watch-areas", response_model=list[WatchAreaRead])
async def list_watch_areas(
    project_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[WatchAreaRead]:
    await owned_project(session, user, project_id)
    rows = (
        await session.execute(
            select(WatchArea, ST_AsGeoJSON(WatchArea.geometry))
            .where(WatchArea.project_id == project_id)
            .order_by(WatchArea.created_at.desc())
        )
    ).all()
    return [
        WatchAreaRead(
            id=area.id,
            project_id=area.project_id,
            name=area.name,
            geometry=json.loads(geometry),
            categories=area.categories,
            schedule=area.schedule,
            is_active=area.is_active,
            last_checked_at=area.last_checked_at,
            created_at=area.created_at,
        )
        for area, geometry in rows
    ]


@router.post(
    "/{project_id}/watch-areas",
    response_model=WatchAreaRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_watch_area(
    project_id: uuid.UUID, payload: WatchAreaCreate, session: SessionDep, user: CurrentUser
) -> WatchAreaRead:
    await owned_project(session, user, project_id)
    geometry_dict = payload.geometry.model_dump()
    area = WatchArea(
        project_id=project_id,
        name=payload.name,
        geometry=from_shape(shape(geometry_dict), srid=4326),
        categories=[category.value for category in payload.categories],
        schedule=payload.schedule,
    )
    session.add(area)
    await session.commit()
    await session.refresh(area)
    return WatchAreaRead(
        id=area.id,
        project_id=area.project_id,
        name=area.name,
        geometry=geometry_dict,
        categories=area.categories,
        schedule=area.schedule,
        is_active=area.is_active,
        last_checked_at=area.last_checked_at,
        created_at=area.created_at,
    )
