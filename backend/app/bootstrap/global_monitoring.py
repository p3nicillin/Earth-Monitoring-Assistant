"""Bootstraps the system-owned "Global Monitoring" project and its coarse,
continent-scale watch areas.

Unlike app.seed's local-dev demo data (gated behind BOOTSTRAP_LOCAL_WORKSPACE
and SQLite-only), this runs unconditionally on every startup, for both SQLite
and Postgres: it is real product infrastructure -- the shared, always-on,
whole-planet monitoring surface -- not throwaway example content.

The owning account (role=system, is_active=False) can never authenticate; it
exists purely as an ownership anchor so the existing owner-scoped Event/
WatchArea model can serve a shared "global" view without weakening per-user
isolation anywhere else. /api/v1/global/* (app.api.global_monitoring) is the
only reader of this project's data, and it is read-only.
"""

import uuid

from shapely.geometry import Polygon
from sqlalchemy import select

from app.core.database import SessionFactory
from app.models.entities import Project, Role, User, WatchArea
from app.utils.geo import shape_to_spatial

GLOBAL_MONITOR_EMAIL = "global-monitor@terralens.system"
GLOBAL_PROJECT_NAME = "Global Monitoring"

# Coarse, generous (west, south, east, north) bounding boxes -- adequate as a STAC
# search radius, not a claim of precise coastline geometry. Antarctica is excluded
# as low monitoring value. Far-eastern Russia/NZ's Pacific extent past +180 is a
# known, accepted simplification of this v1 coarse coverage.
_CONTINENTS: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    ("Africa", (-18.0, -35.0, 52.0, 38.0)),
    ("Asia", (26.0, -12.0, 180.0, 81.0)),
    ("Europe", (-25.0, 34.0, 45.0, 72.0)),
    ("North America", (-170.0, 5.0, -50.0, 75.0)),
    ("South America", (-82.0, -56.0, -34.0, 13.0)),
    ("Oceania", (110.0, -50.0, 180.0, 0.0)),
)

_global_project_id: uuid.UUID | None = None


def _bbox_polygon(bounds: tuple[float, float, float, float]) -> Polygon:
    west, south, east, north = bounds
    return Polygon([(west, south), (east, south), (east, north), (west, north), (west, south)])


async def bootstrap_global_monitoring() -> uuid.UUID:
    """Idempotently ensure the system user/project/watch-areas exist and cache
    the project id for global_monitoring API reads. Safe to call on every
    startup."""
    global _global_project_id
    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == GLOBAL_MONITOR_EMAIL))
        if user is None:
            user = User(
                email=GLOBAL_MONITOR_EMAIL,
                display_name="Global Monitoring (system)",
                # Never authenticates: role=system and is_active=False both
                # independently block login (see app/api/auth.py, app/api/deps.py).
                password_hash="",
                role=Role.system,
                is_active=False,
            )
            session.add(user)
            await session.flush()

        project = await session.scalar(
            select(Project).where(Project.owner_id == user.id, Project.name == GLOBAL_PROJECT_NAME)
        )
        if project is None:
            project = Project(
                owner_id=user.id,
                name=GLOBAL_PROJECT_NAME,
                description=(
                    "System-owned, continent-scale live monitoring shared across all users."
                ),
                color="#22d3ee",
            )
            session.add(project)
            await session.flush()

        existing_names = set(
            (
                await session.scalars(
                    select(WatchArea.name).where(WatchArea.project_id == project.id)
                )
            ).all()
        )
        for name, bounds in _CONTINENTS:
            if name in existing_names:
                continue
            session.add(
                WatchArea(
                    project_id=project.id,
                    name=name,
                    geometry=shape_to_spatial(_bbox_polygon(bounds)),
                    categories=["environment"],
                    schedule="daily",
                )
            )
        await session.commit()
        _global_project_id = project.id
        return project.id


def get_cached_global_project_id() -> uuid.UUID:
    if _global_project_id is None:
        raise RuntimeError(
            "Global monitoring has not been bootstrapped yet; "
            "bootstrap_global_monitoring() must run during application startup"
        )
    return _global_project_id
