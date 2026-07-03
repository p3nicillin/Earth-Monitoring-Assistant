"""Persist normalized space-weather measurements into the metric archive.

Extraction is a pure function over an already-fetched SpaceWeather snapshot;
persistence appends only samples newer than what each series already holds,
so the recorder is idempotent across overlapping upstream windows.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.metrics import (
    KP,
    PROTON_FLUX,
    SOLAR_WIND_BZ,
    SOLAR_WIND_SPEED,
    XRAY_FLUX,
)
from app.models.entities import MetricSample
from app.schemas.solar_system import SpaceWeather


def samples_from_space_weather(weather: SpaceWeather) -> list[tuple[str, datetime, float]]:
    samples: list[tuple[str, datetime, float]] = []
    for point in weather.xray_flux:
        samples.append((XRAY_FLUX.key, point.time_tag, point.flux_watts_m2))
    for entry in weather.kp_index:
        samples.append((KP.key, entry.time_tag, entry.kp))
    for wind in weather.solar_wind:
        if wind.speed_km_s is not None:
            samples.append((SOLAR_WIND_SPEED.key, wind.time_tag, wind.speed_km_s))
        if wind.bz_nt is not None:
            samples.append((SOLAR_WIND_BZ.key, wind.time_tag, wind.bz_nt))
    if weather.proton_flux_10mev_pfu is not None:
        samples.append((PROTON_FLUX.key, weather.generated_at, weather.proton_flux_10mev_pfu))
    return samples


async def record_space_weather(session: AsyncSession, weather: SpaceWeather) -> int:
    """Append new measurements; returns how many samples were stored."""
    samples = samples_from_space_weather(weather)
    if not samples:
        return 0
    metrics = {metric for metric, _, _ in samples}
    latest_rows = (
        await session.execute(
            select(MetricSample.metric, func.max(MetricSample.time_tag))
            .where(MetricSample.metric.in_(metrics))
            .group_by(MetricSample.metric)
        )
    ).all()
    latest: dict[str, datetime] = {}
    for metric, time_tag in latest_rows:
        if time_tag is not None and time_tag.tzinfo is None:
            time_tag = time_tag.replace(tzinfo=UTC)  # SQLite drops tzinfo round-tripping
        latest[metric] = time_tag
    created = 0
    seen: set[tuple[str, datetime]] = set()
    for metric, time_tag, value in samples:
        newest = latest.get(metric)
        if newest is not None and time_tag <= newest:
            continue
        if (metric, time_tag) in seen:
            continue
        seen.add((metric, time_tag))
        session.add(MetricSample(metric=metric, time_tag=time_tag, value=value))
        created += 1
    if created:
        await session.commit()
    return created


async def prune_samples(session: AsyncSession, retention_days: int) -> int:
    """Drop archive rows past retention so an always-on box cannot grow unbounded."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(delete(MetricSample).where(MetricSample.time_tag < cutoff))
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
