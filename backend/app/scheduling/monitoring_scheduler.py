"""Continuous autonomous operation: watch-area ingestion, space-weather
archive/learning ticks, and live space-imagery capture.

The ingestion job periodically runs MonitoringService for watch areas that
are due, instead of only when a user clicks "Search live catalogue".

Single-process (AsyncIOScheduler), matching the "modular monolith" the rest of
this backend already is -- no broker, no separate worker. Three layers guard
against duplicate/overlapping work, each answering a different failure mode:

1. Per-watch-area asyncio.Lock: the same area never double-runs within this
   process if a tick fires while a previous run for that area is still going.
2. Observation's (watch_area_id, source, source_item_id) unique constraint
   (already enforced by the schema): even a race can't create duplicate rows.
3. MonitoringService's event dedup by (detector, before_item_id, after_item_id):
   even a re-run of the same pair can't create a duplicate Event.

Multi-process/horizontal-scale locking (a DB-backed job table) is out of scope;
this backend runs single-process today.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import SessionFactory
from app.imagery.harvester import ImageryHarvester
from app.learning.forecasts import emit_forecasts, resolve_forecasts
from app.learning.recorder import prune_samples, record_space_weather
from app.models.entities import WatchArea
from app.services.feeds import FeedError
from app.services.monitoring import MonitoringService
from app.services.solar_system import SolarSystemService

logger = logging.getLogger(__name__)

_JOB_ID = "monitoring-scheduler-tick"
_LEARNING_JOB_ID = "learning-tick"
_IMAGERY_JOB_ID = "imagery-tick"
_PRUNE_INTERVAL = timedelta(hours=24)

_SCHEDULE_INTERVALS: dict[str, timedelta] = {
    "daily": timedelta(hours=24),
    "weekly": timedelta(days=7),
}


def _is_due(area: WatchArea, now: datetime) -> bool:
    interval = _SCHEDULE_INTERVALS.get(area.schedule)
    if interval is None:  # "manual" and any unrecognized value never auto-run
        return False
    if area.last_checked_at is None:
        return True
    # SQLite does not round-trip tzinfo the way Postgres does, even through a
    # DateTime(timezone=True) column, so last_checked_at can come back naive.
    last_checked_at = area.last_checked_at
    if last_checked_at.tzinfo is None:
        last_checked_at = last_checked_at.replace(tzinfo=UTC)
    return now - last_checked_at >= interval


class MonitoringScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._scheduler = AsyncIOScheduler()
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._semaphore = asyncio.Semaphore(settings.scheduler_max_concurrent_runs)
        self._harvester = ImageryHarvester(settings)
        self._last_prune_at: datetime | None = None

    def start(self) -> None:
        # A startup delay (not an immediate run) keeps this from ever colliding
        # with short-lived TestClient lifespans in the test suite, and avoids a
        # thundering-herd STAC search the instant the server restarts.
        delay = timedelta(seconds=self.settings.scheduler_startup_delay_seconds)
        first_run = datetime.now(UTC) + delay
        self._scheduler.add_job(
            self.run_due_watch_areas,
            trigger="interval",
            seconds=self.settings.scheduler_poll_interval_seconds,
            next_run_time=first_run,
            id=_JOB_ID,
            max_instances=1,
            coalesce=True,
        )
        if self.settings.learning_enabled:
            self._scheduler.add_job(
                self.run_learning_tick,
                trigger="interval",
                seconds=self.settings.learning_interval_seconds,
                next_run_time=first_run,
                id=_LEARNING_JOB_ID,
                max_instances=1,
                coalesce=True,
            )
        if self.settings.imagery_enabled:
            self._scheduler.add_job(
                self.run_imagery_tick,
                trigger="interval",
                seconds=self.settings.imagery_interval_seconds,
                next_run_time=first_run,
                id=_IMAGERY_JOB_ID,
                max_instances=1,
                coalesce=True,
            )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def run_due_watch_areas(self) -> None:
        async with SessionFactory() as session:
            areas = (
                await session.scalars(select(WatchArea).where(WatchArea.is_active.is_(True)))
            ).all()
        now = datetime.now(UTC)
        due = [area for area in areas if _is_due(area, now)]
        if due:
            logger.info("Monitoring scheduler tick: %d watch area(s) due", len(due))
        await asyncio.gather(*(self._run_one(area.id) for area in due))

    async def _run_one(self, area_id: uuid.UUID) -> None:
        lock = self._locks.setdefault(area_id, asyncio.Lock())
        if lock.locked():
            return  # a previous tick's run for this area is still in flight
        async with lock, self._semaphore:
            try:
                async with SessionFactory() as session:
                    area = await session.get(WatchArea, area_id)
                    if area is None or not area.is_active:
                        return
                    geometry_json = await session.scalar(
                        select(ST_AsGeoJSON(WatchArea.geometry)).where(WatchArea.id == area_id)
                    )
                    if geometry_json is None:
                        return
                    outcome = await MonitoringService(session, self.settings).run(
                        area,
                        json.loads(geometry_json),
                        provider_name="planetary-computer",
                        max_cloud_cover=self.settings.detector_cloud_cover_max,
                        lookback_days=self.settings.monitoring_lookback_days,
                        limit=self.settings.provider_max_items,
                    )
                    logger.info(
                        "Scheduled monitoring run for watch area %s: "
                        "%d observation(s), %d event(s)",
                        area_id,
                        outcome.observations_created,
                        outcome.events_created,
                    )
            except Exception:  # noqa: BLE001 - a background job must never crash the scheduler
                logger.warning(
                    "Scheduled monitoring run failed for watch area %s", area_id, exc_info=True
                )

    async def run_learning_tick(self) -> None:
        """Archive the current space-weather state, then score matured forecasts
        and issue fresh ones. Feed outages skip archiving but still resolve."""
        try:
            weather = None
            try:
                weather = await SolarSystemService(self.settings).space_weather()
            except FeedError:
                logger.warning("Learning tick: space weather unavailable; recording skipped")
            async with SessionFactory() as session:
                recorded = 0
                if weather is not None:
                    recorded = await record_space_weather(session, weather)
                resolved = await resolve_forecasts(session, self.settings)
                emitted = await emit_forecasts(session, self.settings)
                pruned = 0
                now = datetime.now(UTC)
                if self._last_prune_at is None or now - self._last_prune_at >= _PRUNE_INTERVAL:
                    pruned = await prune_samples(session, self.settings.learning_retention_days)
                    self._last_prune_at = now
            if recorded or resolved or emitted or pruned:
                logger.info(
                    "Learning tick: %d sample(s) recorded, %d forecast(s) resolved, "
                    "%d issued, %d pruned",
                    recorded,
                    resolved,
                    emitted,
                    pruned,
                )
        except Exception:  # noqa: BLE001 - a background job must never crash the scheduler
            logger.warning("Learning tick failed", exc_info=True)

    async def run_imagery_tick(self) -> None:
        try:
            stored = await self._harvester.capture_all()
            if stored:
                logger.info("Imagery tick: %d new frame(s) archived", stored)
        except Exception:  # noqa: BLE001 - a background job must never crash the scheduler
            logger.warning("Imagery tick failed", exc_info=True)
