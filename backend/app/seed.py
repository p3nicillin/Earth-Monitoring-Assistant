import asyncio
from datetime import UTC, datetime, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models.entities import (
    Event,
    EventCategory,
    Project,
    ReviewOutcome,
    Role,
    Severity,
    User,
    WatchArea,
)


async def seed_demo_data() -> None:
    settings = get_settings()
    if not settings.seed_demo_data:
        return
    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == str(settings.demo_user_email)))
        if user is None:
            user = User(
                email=str(settings.demo_user_email),
                display_name="Demo Analyst",
                password_hash=hash_password(settings.demo_user_password),
                role=Role.analyst,
            )
            session.add(user)
            await session.flush()
        project = await session.scalar(
            select(Project).where(Project.owner_id == user.id, Project.name == "UK Climate Watch")
        )
        if project is not None:
            await session.commit()
            return
        project = Project(
            owner_id=user.id,
            name="UK Climate Watch",
            description="Demonstration monitoring project covering environmental and urban change.",
            color="#4ade80",
        )
        session.add(project)
        await session.flush()
        area_polygon = Polygon([(-3.7, 50.8), (1.8, 50.8), (1.8, 54.0), (-3.7, 54.0), (-3.7, 50.8)])
        area = WatchArea(
            project_id=project.id,
            name="Southern Britain",
            geometry=from_shape(area_polygon, srid=4326),
            categories=["environment", "urban", "disaster"],
            schedule="daily",
            last_checked_at=datetime.now(UTC) - timedelta(hours=2),
        )
        session.add(area)
        event_specs = [
            (
                "Flood extent increased",
                "flood_extent",
                EventCategory.disaster,
                Severity.high,
                0.91,
                Polygon(
                    [(-2.42, 51.75), (-2.15, 51.75), (-2.15, 51.94), (-2.42, 51.94), (-2.42, 51.75)]
                ),
                23.4,
                4,
            ),
            (
                "Vegetation cover decline",
                "vegetation_change",
                EventCategory.environment,
                Severity.medium,
                0.84,
                Polygon(
                    [(-0.92, 52.42), (-0.65, 52.42), (-0.65, 52.63), (-0.92, 52.63), (-0.92, 52.42)]
                ),
                17.8,
                13,
            ),
            (
                "New construction footprint",
                "new_construction",
                EventCategory.urban,
                Severity.low,
                0.78,
                Polygon(
                    [(-1.42, 51.31), (-1.28, 51.31), (-1.28, 51.42), (-1.42, 51.42), (-1.42, 51.31)]
                ),
                4.2,
                28,
            ),
        ]
        for (
            title,
            event_type,
            category,
            severity,
            confidence,
            geometry,
            area_km,
            age,
        ) in event_specs:
            reviewed = age == 13
            session.add(
                Event(
                    project_id=project.id,
                    title=title,
                    summary=(
                        "Demonstration detection generated for interface evaluation. "
                        "Inspect evidence before use."
                    ),
                    event_type=event_type,
                    category=category,
                    severity=severity,
                    confidence=confidence,
                    geometry=from_shape(geometry, srid=4326),
                    area_sq_km=area_km,
                    detected_at=datetime.now(UTC) - timedelta(hours=age),
                    detector_name="seed-demo-detector",
                    detector_version="1.0.0",
                    evidence={"mode": "seed-demo", "requires_human_review": True},
                    is_reviewed=reviewed,
                    review_outcome=(
                        ReviewOutcome.confirmed if reviewed else ReviewOutcome.unreviewed
                    ),
                    reviewed_by_id=user.id if reviewed else None,
                    reviewed_at=datetime.now(UTC) - timedelta(hours=2) if reviewed else None,
                    review_note="Confirmed against the source observation." if reviewed else None,
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
