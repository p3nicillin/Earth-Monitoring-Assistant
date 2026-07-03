"""Gallery access to the autonomously archived space imagery."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.imagery.sources import IMAGERY_SOURCES
from app.models.entities import ImageryCapture
from app.schemas.imagery import ImageryCaptureRead, ImageryGallery, ImagerySourceStatus

router = APIRouter(prefix="/imagery", tags=["space imagery archive"])


@router.get("/sources", response_model=list[ImagerySourceStatus])
async def sources(user: CurrentUser, session: SessionDep) -> list[ImagerySourceStatus]:
    del user
    rows = (
        await session.execute(
            select(
                ImageryCapture.source_key,
                func.count(ImageryCapture.id),
                func.max(ImageryCapture.captured_at),
            ).group_by(ImageryCapture.source_key)
        )
    ).all()
    stats = {key: (count, latest) for key, count, latest in rows}
    statuses: list[ImagerySourceStatus] = []
    for source in IMAGERY_SOURCES:
        count, latest = stats.get(source.key, (0, None))
        latest_id = None
        if count:
            latest_id = await session.scalar(
                select(ImageryCapture.id)
                .where(ImageryCapture.source_key == source.key)
                .order_by(ImageryCapture.captured_at.desc())
                .limit(1)
            )
        statuses.append(
            ImagerySourceStatus(
                key=source.key,
                title=source.title,
                source=source.source,
                description=source.description,
                capture_count=int(count),
                latest_captured_at=latest,
                latest_capture_id=latest_id,
            )
        )
    return statuses


@router.get("/captures", response_model=ImageryGallery)
async def captures(
    user: CurrentUser,
    session: SessionDep,
    source_key: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImageryGallery:
    del user
    filters = [ImageryCapture.source_key == source_key] if source_key else []
    total = await session.scalar(select(func.count(ImageryCapture.id)).where(*filters))
    rows = (
        await session.scalars(
            select(ImageryCapture)
            .where(*filters)
            .order_by(ImageryCapture.captured_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return ImageryGallery(
        generated_at=datetime.now(UTC),
        total=int(total or 0),
        items=[ImageryCaptureRead.model_validate(row) for row in rows],
    )


def _resolve_capture_path(imagery_dir: str, file_path: str) -> Path | None:
    base_dir = Path(imagery_dir).resolve()
    target = (base_dir / file_path).resolve()
    # file_path is server-generated, but never serve outside the archive root.
    if not target.is_relative_to(base_dir) or not target.is_file():
        return None
    return target


@router.get("/captures/{capture_id}/file")
async def capture_file(capture_id: uuid.UUID, session: SessionDep) -> FileResponse:
    # Deliberately unauthenticated: plain <img> tags cannot attach bearer
    # headers, and every frame here is redistributable public NASA/NOAA/ESA
    # imagery addressed by an unguessable UUID. Listing/metadata stays gated.
    capture = await session.get(ImageryCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    target = await run_in_threadpool(
        _resolve_capture_path, get_settings().imagery_dir, capture.file_path
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Capture file is missing")
    return FileResponse(
        target,
        media_type=capture.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
