import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Project, User, WatchArea


async def owned_project(session: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def owned_watch_area(
    session: AsyncSession, user: User, watch_area_id: uuid.UUID
) -> WatchArea:
    watch_area = await session.scalar(
        select(WatchArea)
        .join(Project)
        .where(WatchArea.id == watch_area_id, Project.owner_id == user.id)
    )
    if watch_area is None:
        raise HTTPException(status_code=404, detail="Watch area not found")
    return watch_area
