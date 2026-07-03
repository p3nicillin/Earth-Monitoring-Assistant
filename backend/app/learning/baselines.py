"""Quantile climatology learned from the recorded metric archive.

The adaptive threshold starts at the published operational floor and, once a
metric has at least `learning_min_baseline_samples` of local history, may
tighten toward the observed p99 (or p1 for low-side metrics like Bz). It can
only ever be as strict as or stricter than the published floor, so learning
adds sensitivity to locally unusual conditions without ever suppressing a
NOAA-scale alert.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SessionFactory
from app.learning.metrics import METRIC_SPECS, MetricSpec
from app.models.entities import MetricSample
from app.schemas.insights import MetricBaseline

_BASELINE_CACHE_TTL_SECONDS = 600.0

_cache: tuple[float, list[MetricBaseline]] | None = None
_cache_lock = asyncio.Lock()


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile over an ascending list (q in 0..100)."""
    if not sorted_values:
        raise ValueError("percentile() requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q / 100.0
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def build_baseline(
    spec: MetricSpec,
    values: list[float],
    time_tags: list[datetime],
    *,
    window_days: int,
    min_samples: int,
) -> MetricBaseline:
    ordered = sorted(values)
    count = len(ordered)
    mature = count >= min_samples
    adaptive: float | None = None
    p95: float | None = None
    p99: float | None = None
    extreme: float | None = None
    if count:
        if spec.direction == "high":
            p95 = percentile(ordered, 95.0)
            p99 = percentile(ordered, 99.0)
            extreme = ordered[-1]
            if mature:
                adaptive = max(spec.published_floor, p99)
        else:
            p95 = percentile(ordered, 5.0)
            p99 = percentile(ordered, 1.0)
            extreme = ordered[0]
            if mature:
                adaptive = min(spec.published_floor, p99)
    return MetricBaseline(
        metric=spec.key,
        title=spec.title,
        unit=spec.unit,
        direction=spec.direction,
        sample_count=count,
        window_days=window_days,
        first_sample_at=min(time_tags) if time_tags else None,
        last_sample_at=max(time_tags) if time_tags else None,
        mean=sum(ordered) / count if count else None,
        p50=percentile(ordered, 50.0) if count else None,
        p95=p95,
        p99=p99,
        observed_extreme=extreme,
        published_floor=spec.published_floor,
        adaptive_threshold=adaptive,
        maturity=min(1.0, count / min_samples) if min_samples > 0 else 1.0,
    )


async def compute_baselines(session: AsyncSession, settings: Settings) -> list[MetricBaseline]:
    window_days = settings.learning_baseline_window_days
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    baselines: list[MetricBaseline] = []
    for spec in METRIC_SPECS:
        rows = (
            await session.execute(
                select(MetricSample.time_tag, MetricSample.value).where(
                    MetricSample.metric == spec.key, MetricSample.time_tag >= cutoff
                )
            )
        ).all()
        time_tags = [tag if tag.tzinfo is not None else tag.replace(tzinfo=UTC) for tag, _ in rows]
        values = [value for _, value in rows]
        baselines.append(
            build_baseline(
                spec,
                values,
                time_tags,
                window_days=window_days,
                min_samples=settings.learning_min_baseline_samples,
            )
        )
    return baselines


async def cached_baselines(settings: Settings) -> list[MetricBaseline]:
    """Baselines for hot paths (overview/stream): recomputed at most every 10
    minutes, and never allowed to break the caller if the archive is unavailable."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _BASELINE_CACHE_TTL_SECONDS:
        return _cache[1]
    async with _cache_lock:
        if _cache is not None and time.monotonic() - _cache[0] < _BASELINE_CACHE_TTL_SECONDS:
            return _cache[1]
        try:
            async with SessionFactory() as session:
                baselines = await compute_baselines(session, settings)
        except Exception:  # pragma: no cover - degraded-DB path
            return _cache[1] if _cache is not None else []
        _cache = (time.monotonic(), baselines)
        return baselines


def clear_baseline_cache() -> None:
    """Reset the in-process cache; intended for tests."""
    global _cache
    _cache = None
