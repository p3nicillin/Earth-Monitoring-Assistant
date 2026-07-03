"""Imagery harvester: content-hash dedupe, bounded pruning, content-type
gating, and archive-root path safety."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.imagery import _resolve_capture_path
from app.core.config import Settings
from app.imagery import harvester as harvester_module
from app.imagery.harvester import ImageryHarvester
from app.imagery.sources import SOURCES_BY_KEY, resolve_frame
from app.models.entities import ImageryCapture


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "image/png") -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requested: list[str] = []

    async def get(self, url: str) -> FakeResponse:
        self.requested.append(url)
        return self.response


async def make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: ImageryCapture.__table__.create(sync))
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def capture_with(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    responses: list[FakeResponse],
    max_per_source: int = 10,
) -> tuple[int, list[Any], list[Path]]:
    """Run one _capture_one per response against a shared in-memory archive."""
    settings = Settings(imagery_dir=str(tmp_path), imagery_max_captures_per_source=max_per_source)
    source = SOURCES_BY_KEY["sdo-aia-193"]

    async def scenario() -> tuple[int, list[Any]]:
        factory = await make_session_factory()
        monkeypatch.setattr(harvester_module, "SessionFactory", factory)
        harvester = ImageryHarvester(settings)
        stored = 0
        for response in responses:
            stored += await harvester._capture_one(FakeClient(response), source)  # type: ignore[arg-type]
        async with factory() as session:
            rows = (await session.scalars(select(ImageryCapture))).all()
        return stored, rows

    stored, rows = asyncio.run(scenario())
    return stored, rows, sorted(tmp_path.rglob("*.*"))


def test_capture_dedupes_identical_frames(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frame = FakeResponse(b"png-bytes-1")
    stored, rows, files = capture_with(monkeypatch, tmp_path, [frame, frame])
    assert stored == 1
    assert len(rows) == 1
    assert len(files) == 1
    assert rows[0].byte_size == len(b"png-bytes-1")
    assert files[0].read_bytes() == b"png-bytes-1"


def test_capture_stores_each_distinct_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stored, rows, files = capture_with(
        monkeypatch, tmp_path, [FakeResponse(b"frame-a"), FakeResponse(b"frame-b")]
    )
    assert stored == 2
    assert len(rows) == 2
    assert len(files) == 2


def test_capture_prunes_to_configured_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stored, rows, files = capture_with(
        monkeypatch,
        tmp_path,
        [FakeResponse(b"frame-a"), FakeResponse(b"frame-b"), FakeResponse(b"frame-c")],
        max_per_source=1,
    )
    assert stored == 3
    assert len(rows) == 1  # only the newest row survives
    assert len(files) == 1  # pruned frames are deleted from disk too


def test_capture_rejects_non_image_content(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stored, rows, files = capture_with(
        monkeypatch, tmp_path, [FakeResponse(b"<html>oops</html>", content_type="text/html")]
    )
    assert stored == 0
    assert rows == []
    assert files == []


def test_capture_rejects_oversized_frames(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = Settings(imagery_dir=str(tmp_path), imagery_max_bytes=4)
    source = SOURCES_BY_KEY["sdo-aia-193"]

    async def scenario() -> int:
        factory = await make_session_factory()
        monkeypatch.setattr(harvester_module, "SessionFactory", factory)
        harvester = ImageryHarvester(settings)
        return await harvester._capture_one(
            FakeClient(FakeResponse(b"way-more-than-four-bytes")),  # type: ignore[arg-type]
            source,
        )

    assert asyncio.run(scenario()) == 0


def test_static_sources_resolve_without_network() -> None:
    settings = Settings()
    source = SOURCES_BY_KEY["soho-lasco-c3"]
    frame = asyncio.run(resolve_frame(settings, source))
    assert frame is not None
    assert frame.url == source.static_url


def test_resolve_capture_path_refuses_archive_escape(tmp_path: Path) -> None:
    inside = tmp_path / "sdo" / "frame.png"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"x")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    assert _resolve_capture_path(str(tmp_path), "sdo/frame.png") == inside
    assert _resolve_capture_path(str(tmp_path), "../secret.txt") is None
    assert _resolve_capture_path(str(tmp_path), "missing.png") is None
