import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import Settings
from app.models.entities import WatchArea
from app.scheduling import monitoring_scheduler as scheduler_module
from app.scheduling.monitoring_scheduler import MonitoringScheduler, _is_due

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-1.0, 51.0], [0.0, 51.0], [0.0, 52.0], [-1.0, 52.0], [-1.0, 51.0]]],
}


def _settings() -> Settings:
    return Settings(secret_key="x" * 32)


def _area(*, schedule: str, last_checked_at: datetime | None = None) -> WatchArea:
    return WatchArea(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Area",
        geometry=GEOMETRY,
        categories=[],
        schedule=schedule,
        is_active=True,
        last_checked_at=last_checked_at,
    )


def test_is_due_daily_schedule() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert _is_due(_area(schedule="daily", last_checked_at=now - timedelta(hours=25)), now) is True
    assert _is_due(_area(schedule="daily", last_checked_at=now - timedelta(hours=1)), now) is False
    assert _is_due(_area(schedule="daily", last_checked_at=None), now) is True


def test_is_due_weekly_schedule() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert _is_due(_area(schedule="weekly", last_checked_at=now - timedelta(days=8)), now) is True
    assert _is_due(_area(schedule="weekly", last_checked_at=now - timedelta(days=1)), now) is False


def test_is_due_handles_timezone_naive_last_checked_at() -> None:
    # Regression: SQLite does not round-trip tzinfo through DateTime(timezone=True),
    # so last_checked_at can come back naive in practice (caught via manual E2E
    # verification against a real SQLite-backed run, not by the aware-only tests
    # above).
    now = datetime(2026, 1, 10, tzinfo=UTC)
    stale_naive = (now - timedelta(hours=25)).replace(tzinfo=None)
    fresh_naive = (now - timedelta(hours=1)).replace(tzinfo=None)
    assert _is_due(_area(schedule="daily", last_checked_at=stale_naive), now) is True
    assert _is_due(_area(schedule="daily", last_checked_at=fresh_naive), now) is False


def test_is_due_manual_schedule_never_triggers() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert _is_due(_area(schedule="manual", last_checked_at=None), now) is False


def test_is_due_unrecognized_schedule_never_triggers() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert _is_due(_area(schedule="hourly", last_checked_at=None), now) is False


class _FakeSessionCtx:
    def __init__(self, area: WatchArea) -> None:
        self._area = area

    async def __aenter__(self) -> "_FakeSessionCtx":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, _model: Any, _id: uuid.UUID) -> WatchArea:
        return self._area

    async def scalar(self, _stmt: Any) -> str:
        return json.dumps(self._area.geometry)


def test_overlap_guard_skips_concurrent_run_for_same_area(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _area(schedule="daily", last_checked_at=None)
    monkeypatch.setattr(scheduler_module, "SessionFactory", lambda: _FakeSessionCtx(area))

    call_count = 0

    async def slow_run(
        self: Any, area_arg: WatchArea, geometry: dict[str, Any], **kwargs: Any
    ) -> None:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr("app.services.monitoring.MonitoringService.run", slow_run)

    scheduler = MonitoringScheduler(_settings())

    async def trigger_twice() -> None:
        await asyncio.gather(scheduler._run_one(area.id), scheduler._run_one(area.id))

    asyncio.run(trigger_twice())

    assert call_count == 1


def test_run_due_watch_areas_only_triggers_due_areas(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    due_area = _area(schedule="daily", last_checked_at=now - timedelta(hours=48))
    fresh_area = _area(schedule="daily", last_checked_at=now - timedelta(minutes=5))
    manual_area = _area(schedule="manual", last_checked_at=None)

    class _ListSessionCtx:
        async def __aenter__(self) -> "_ListSessionCtx":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def scalars(self, _stmt: Any) -> Any:
            class _Result:
                def all(self_inner) -> list[WatchArea]:
                    return [due_area, fresh_area, manual_area]

            return _Result()

    monkeypatch.setattr(scheduler_module, "SessionFactory", lambda: _ListSessionCtx())

    triggered: list[uuid.UUID] = []

    async def fake_run_one(self: MonitoringScheduler, area_id: uuid.UUID) -> None:
        triggered.append(area_id)

    monkeypatch.setattr(MonitoringScheduler, "_run_one", fake_run_one)

    scheduler = MonitoringScheduler(_settings())
    asyncio.run(scheduler.run_due_watch_areas())

    assert triggered == [due_area.id]
