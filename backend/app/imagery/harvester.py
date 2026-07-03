"""Fetch, deduplicate, store, and prune live space imagery frames.

Per-source failures degrade that source only. A frame is stored once per
distinct content hash; re-fetching an unchanged upstream "latest" URL is a
no-op, so the archive grows exactly as fast as the sky actually changes.
"""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SessionFactory
from app.imagery.sources import IMAGERY_SOURCES, ImagerySource, ResolvedFrame, resolve_frame
from app.models.entities import ImageryCapture
from app.services.feeds import USER_AGENT

logger = logging.getLogger(__name__)

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class ImageryHarvester:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_dir = Path(settings.imagery_dir)

    async def capture_all(self) -> int:
        """Capture every registered source; returns frames newly stored."""
        stored = 0
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for source in IMAGERY_SOURCES:
                try:
                    stored += await self._capture_one(client, source)
                except Exception:  # noqa: BLE001 - one source must not break the sweep
                    logger.warning("Imagery capture failed for %s", source.key, exc_info=True)
        return stored

    async def _capture_one(self, client: httpx.AsyncClient, source: ImagerySource) -> int:
        frame = await resolve_frame(self.settings, source)
        if frame is None:
            return 0
        response = await client.get(frame.url)
        response.raise_for_status()
        content = response.content
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not content or len(content) > self.settings.imagery_max_bytes:
            return 0
        if content_type not in _CONTENT_TYPE_EXTENSIONS:
            logger.warning(
                "Imagery source %s returned unexpected content type %r", source.key, content_type
            )
            return 0
        content_hash = hashlib.sha256(content).hexdigest()
        async with SessionFactory() as session:
            exists = await session.scalar(
                select(ImageryCapture.id).where(
                    ImageryCapture.source_key == source.key,
                    ImageryCapture.content_hash == content_hash,
                )
            )
            if exists is not None:
                return 0
            captured_at = frame.captured_at or datetime.now(UTC)
            relative_path = self._write_file(
                source, frame, captured_at, content, content_hash, content_type
            )
            session.add(
                ImageryCapture(
                    source_key=source.key,
                    title=source.title,
                    source=source.source,
                    upstream_url=frame.url,
                    captured_at=captured_at,
                    content_hash=content_hash,
                    file_path=relative_path,
                    byte_size=len(content),
                    content_type=content_type,
                    metadata_json={"description": source.description, **frame.metadata},
                )
            )
            await session.commit()
            await self._prune_source(session, source.key)
        return 1

    def _write_file(
        self,
        source: ImagerySource,
        frame: ResolvedFrame,
        captured_at: datetime,
        content: bytes,
        content_hash: str,
        content_type: str,
    ) -> str:
        del frame
        extension = _CONTENT_TYPE_EXTENSIONS[content_type]
        stamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
        relative = Path(source.key) / f"{stamp}_{content_hash[:10]}{extension}"
        absolute = self.base_dir / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(content)
        return relative.as_posix()

    async def _prune_source(self, session: AsyncSession, source_key: str) -> None:
        limit = self.settings.imagery_max_captures_per_source
        rows = (
            await session.scalars(
                select(ImageryCapture)
                .where(ImageryCapture.source_key == source_key)
                .order_by(ImageryCapture.captured_at.desc())
                .offset(limit)
            )
        ).all()
        if not rows:
            return
        for row in rows:
            target = self.base_dir / row.file_path
            try:
                target.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete pruned imagery file %s", target)
            await session.delete(row)
        await session.commit()
