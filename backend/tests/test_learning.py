"""Adaptive-learning layer: recorder idempotence, baseline math, forecast
models, self-scoring, and adaptive anomaly gating."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.learning.anomalies import detect_adaptive_anomalies
from app.learning.baselines import build_baseline, compute_baselines, percentile
from app.learning.forecasts import (
    DAMPED_TREND,
    PERSISTENCE,
    damped_trend_prediction,
    emit_forecasts,
    forecast_skill,
    resolve_forecasts,
)
from app.learning.metrics import KP, SOLAR_WIND_BZ, SOLAR_WIND_SPEED
from app.learning.recorder import prune_samples, record_space_weather, samples_from_space_weather
from app.models.entities import MetricForecast, MetricSample
from app.schemas.insights import MetricBaseline
from app.schemas.solar_system import KpEntry, SolarWindPoint, SpaceWeather, XrayFluxPoint

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


async def make_session_factory() -> async_sessionmaker[AsyncSession]:
    """In-memory database with only the learning tables; created inside the
    running loop because aiosqlite connections are loop-bound."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: MetricSample.__table__.create(sync))
        await connection.run_sync(lambda sync: MetricForecast.__table__.create(sync))
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def make_weather(
    kp_values: list[float] | None = None,
    wind_speeds: list[float] | None = None,
    proton_flux: float | None = None,
) -> SpaceWeather:
    kp_values = kp_values if kp_values is not None else [2.0, 3.0]
    wind_speeds = wind_speeds if wind_speeds is not None else []
    return SpaceWeather(
        source="test",
        generated_at=NOW,
        cache_expires_at=NOW + timedelta(minutes=1),
        xray_flux=[
            XrayFluxPoint(time_tag=NOW - timedelta(minutes=10), flux_watts_m2=2.5e-7),
            XrayFluxPoint(time_tag=NOW - timedelta(minutes=5), flux_watts_m2=3.0e-7),
        ],
        current_xray_class="B3.0",
        latest_flare=None,
        kp_index=[
            KpEntry(time_tag=NOW - timedelta(hours=len(kp_values) - index), kp=value)
            for index, value in enumerate(kp_values)
        ],
        current_kp=kp_values[-1] if kp_values else None,
        solar_wind=[
            SolarWindPoint(
                time_tag=NOW - timedelta(minutes=10 * (len(wind_speeds) - index)),
                speed_km_s=speed,
                bz_nt=-2.0,
            )
            for index, speed in enumerate(wind_speeds)
        ],
        current_solar_wind=(
            SolarWindPoint(time_tag=NOW, speed_km_s=wind_speeds[-1], bz_nt=-2.0)
            if wind_speeds
            else None
        ),
        proton_flux_10mev_pfu=proton_flux,
    )


def test_samples_from_space_weather_extracts_all_series() -> None:
    weather = make_weather(kp_values=[2.0, 4.0], wind_speeds=[400.0], proton_flux=0.5)
    samples = samples_from_space_weather(weather)
    metrics = {metric for metric, _, _ in samples}
    assert metrics == {
        "kp",
        "xray_long_wm2",
        "solar_wind_speed_kms",
        "solar_wind_bz_nt",
        "proton_flux_10mev_pfu",
    }


def test_record_space_weather_is_idempotent() -> None:
    weather = make_weather(kp_values=[2.0, 4.0], wind_speeds=[420.0])

    async def scenario() -> tuple[int, int]:
        factory = await make_session_factory()
        async with factory() as session:
            first = await record_space_weather(session, weather)
        async with factory() as session:
            second = await record_space_weather(session, weather)
        return first, second

    first, second = asyncio.run(scenario())
    assert first > 0
    assert second == 0


def test_prune_samples_removes_only_expired_rows() -> None:
    async def scenario() -> int:
        factory = await make_session_factory()
        async with factory() as session:
            session.add(
                MetricSample(
                    metric=KP.key, time_tag=datetime.now(UTC) - timedelta(days=400), value=1.0
                )
            )
            session.add(MetricSample(metric=KP.key, time_tag=datetime.now(UTC), value=2.0))
            await session.commit()
            return await prune_samples(session, retention_days=365)

    assert asyncio.run(scenario()) == 1


def test_percentile_interpolates() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 50.0) == pytest.approx(2.5)
    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 100.0) == 4.0
    with pytest.raises(ValueError):
        percentile([], 50.0)


def test_build_baseline_needs_min_samples_for_adaptive_threshold() -> None:
    tags = [NOW - timedelta(hours=index) for index in range(10)]
    baseline = build_baseline(KP, [2.0] * 10, tags, window_days=60, min_samples=100)
    assert baseline.adaptive_threshold is None
    assert baseline.maturity == pytest.approx(0.1)


def test_build_baseline_high_side_never_relaxes_published_floor() -> None:
    # Quiet history: p99 well below the G1 floor of Kp 5 -> threshold stays 5.
    tags = [NOW - timedelta(hours=index) for index in range(200)]
    baseline = build_baseline(KP, [2.0] * 200, tags, window_days=60, min_samples=100)
    assert baseline.adaptive_threshold == KP.published_floor


def test_build_baseline_low_side_uses_p1_for_bz() -> None:
    values = [-30.0] * 10 + [0.0] * 190  # active history: p1 below the -10 floor
    tags = [NOW - timedelta(hours=index) for index in range(200)]
    baseline = build_baseline(SOLAR_WIND_BZ, values, tags, window_days=60, min_samples=100)
    assert baseline.adaptive_threshold is not None
    assert baseline.adaptive_threshold <= SOLAR_WIND_BZ.published_floor


def test_damped_trend_dampens_toward_persistence() -> None:
    points = [(NOW - timedelta(hours=5 - index), 400.0 + 20.0 * index) for index in range(6)]
    short = damped_trend_prediction(points, 3.0)
    long = damped_trend_prediction(points, 24.0)
    assert short is not None and long is not None
    assert short > points[-1][1]  # rising trend extrapolates upward
    assert abs(long - points[-1][1]) < abs(short - points[-1][1]) * 8  # damped, not linear
    assert damped_trend_prediction(points[:3], 3.0) is None  # too few points


def test_emit_resolve_and_score_forecasts() -> None:
    settings = Settings(learning_forecast_horizons_hours=[3])

    async def scenario() -> tuple[int, int, list]:
        factory = await make_session_factory()
        made_at = NOW
        async with factory() as session:
            for index in range(12):
                session.add(
                    MetricSample(
                        metric=KP.key,
                        time_tag=made_at - timedelta(minutes=30 * (12 - index)),
                        value=2.0 + 0.1 * index,
                    )
                )
                session.add(
                    MetricSample(
                        metric=SOLAR_WIND_SPEED.key,
                        time_tag=made_at - timedelta(minutes=30 * (12 - index)),
                        value=420.0,
                    )
                )
            await session.commit()
            emitted = await emit_forecasts(session, settings, now=made_at)
            # A second emission within the hourly spacing must be a no-op.
            assert await emit_forecasts(session, settings, now=made_at) == 0
            # The observations that later arrive at the target time:
            session.add(
                MetricSample(metric=KP.key, time_tag=made_at + timedelta(hours=3), value=3.4)
            )
            session.add(
                MetricSample(
                    metric=SOLAR_WIND_SPEED.key,
                    time_tag=made_at + timedelta(hours=3),
                    value=430.0,
                )
            )
            await session.commit()
            resolved = await resolve_forecasts(session, settings, now=made_at + timedelta(hours=4))
            skill = await forecast_skill(session)
        return emitted, resolved, skill

    emitted, resolved, skill = asyncio.run(scenario())
    assert emitted == 4  # 2 metrics x (persistence + damped-trend) x 1 horizon
    assert resolved == 4
    models = {(item.metric, item.model_name) for item in skill}
    assert (KP.key, PERSISTENCE) in models
    assert (KP.key, DAMPED_TREND) in models
    trend_entries = [item for item in skill if item.model_name == DAMPED_TREND]
    assert all(item.skill_vs_persistence is not None for item in trend_entries)


def test_compute_baselines_covers_every_metric() -> None:
    settings = Settings()

    async def scenario() -> list[MetricBaseline]:
        factory = await make_session_factory()
        async with factory() as session:
            return await compute_baselines(session, settings)

    baselines = asyncio.run(scenario())
    assert len(baselines) == 5
    assert all(item.sample_count == 0 for item in baselines)


def _baseline(metric: str, threshold: float, direction: str) -> MetricBaseline:
    return MetricBaseline(
        metric=metric,
        title=metric,
        unit="u",
        direction=direction,  # type: ignore[arg-type]
        sample_count=500,
        window_days=60,
        first_sample_at=NOW - timedelta(days=30),
        last_sample_at=NOW,
        mean=2.0,
        p50=2.0,
        p95=3.0,
        p99=threshold,
        observed_extreme=threshold,
        published_floor=5.0 if direction == "high" else -10.0,
        adaptive_threshold=threshold,
        maturity=1.0,
    )


def test_adaptive_anomaly_fires_only_beyond_learned_threshold() -> None:
    weather = make_weather(kp_values=[2.0, 4.6])
    quiet = detect_adaptive_anomalies(weather, [_baseline("kp", 4.8, "high")])
    assert quiet == []
    active = detect_adaptive_anomalies(weather, [_baseline("kp", 4.5, "high")])
    assert len(active) == 1
    detection = active[0]
    assert detection.detector == "adaptive-baseline"
    # Above the learned threshold but below the published G1 floor: early watch.
    assert detection.severity == "watch"
    assert detection.metrics["learned_threshold"] == 4.5


def test_adaptive_anomaly_upgrades_to_warning_beyond_published_floor() -> None:
    weather = make_weather(kp_values=[2.0, 6.0])
    detections = detect_adaptive_anomalies(weather, [_baseline("kp", 4.5, "high")])
    assert len(detections) == 1
    assert detections[0].severity == "warning"
