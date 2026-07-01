import asyncio

from shapely.geometry import Polygon
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models.entities import Project, Role, User, WatchArea
from app.utils.geo import shape_to_spatial


async def bootstrap_local_workspace() -> None:
    settings = get_settings()
    if not settings.bootstrap_local_workspace:
        return
    async with SessionFactory() as session:
        user = await session.scalar(
            select(User).where(User.email == str(settings.local_user_email))
        )
        if user is None:
            user = User(
                email=str(settings.local_user_email),
                display_name="Earth Analyst",
                password_hash=hash_password(settings.local_user_password),
                role=Role.analyst,
            )
            session.add(user)
            await session.flush()
        project = await session.scalar(
            select(Project).where(Project.owner_id == user.id, Project.name == "UK Sentinel Watch")
        )
        if project is not None:
            await session.commit()
            return
        project = Project(
            owner_id=user.id,
            name="UK Sentinel Watch",
            description="Sentinel-2 catalogue monitoring for environmental change across the UK.",
            color="#4ade80",
        )
        session.add(project)
        await session.flush()
        area_polygon = Polygon([(-3.7, 50.8), (1.8, 50.8), (1.8, 54.0), (-3.7, 54.0), (-3.7, 50.8)])
        area = WatchArea(
            project_id=project.id,
            name="Southern Britain",
            geometry=shape_to_spatial(area_polygon),
            categories=["environment", "agriculture", "disaster"],
            schedule="daily",
        )
        session.add(area)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(bootstrap_local_workspace())
