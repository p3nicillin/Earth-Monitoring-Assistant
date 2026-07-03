"""Short-horizon statistical forecasts with measured self-scoring.

Two models run side by side on every forecastable metric:

- ``persistence`` — the naive control: the next value equals the last value.
- ``damped-trend`` — least-squares slope over the recent window, damped
  toward zero with horizon so long extrapolations converge to persistence.

Every forecast row is stored, then resolved against the observed sample
closest to its target time. The ratio of damped-trend error to persistence
error is the system's honest, accumulating measure of whether its model is
actually better than guessing — this is the feedback loop that makes the
platform's "self-improvement" quantifiable rather than rhetorical.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.learning.metrics import FORECASTABLE_METRICS, METRICS_BY_KEY, MetricSpec
from app.models.entities import MetricForecast, MetricSample
from app.schemas.insights import ForecastSkill

MODEL_VERSION = "1.0.0"
PERSISTENCE = "persistence"
DAMPED_TREND = "damped-trend"

_TREND_WINDOW = timedelta(hours=6)
_TREND_DAMPING_PER_HOUR = 0.85
_MIN_TREND_POINTS = 6
_EMIT_SPACING = timedelta(minutes=55)
_RESOLVE_LOOKBACK = timedelta(days=7)


def _clamp(spec: MetricSpec, value: float) -> float:
    if spec.minimum is not None:
        value = max(spec.minimum, value)
    if spec.maximum is not None:
        value = min(spec.maximum, value)
    return value


def damped_trend_prediction(
    points: list[tuple[datetime, float]], horizon_hours: float
) -> float | None:
    """Least-squares slope over the window, damped exponentially with horizon."""
    if len(points) < _MIN_TREND_POINTS:
        return None
    reference = points[-1][0]
    xs = [(tag - reference).total_seconds() / 3600.0 for tag, _ in points]
    ys = [value for _, value in points]
    n = len(points)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denominator
    damping = float(_TREND_DAMPING_PER_HOUR**horizon_hours)
    return ys[-1] + slope * horizon_hours * damping


async def emit_forecasts(
    session: AsyncSession, settings: Settings, now: datetime | None = None
) -> int:
    """Issue a fresh forecast set unless one was issued within the last hour."""
    reference = now or datetime.now(UTC)
    last_made = await session.scalar(select(func.max(MetricForecast.made_at)))
    if last_made is not None:
        if last_made.tzinfo is None:
            last_made = last_made.replace(tzinfo=UTC)
        if reference - last_made < _EMIT_SPACING:
            return 0
    created = 0
    for spec in FORECASTABLE_METRICS:
        rows = (
            await session.execute(
                select(MetricSample.time_tag, MetricSample.value)
                .where(
                    MetricSample.metric == spec.key,
                    MetricSample.time_tag >= reference - _TREND_WINDOW,
                )
                .order_by(MetricSample.time_tag)
            )
        ).all()
        points = [
            (tag if tag.tzinfo is not None else tag.replace(tzinfo=UTC), value)
            for tag, value in rows
        ]
        if not points:
            continue
        last_value = points[-1][1]
        for horizon_hours in settings.learning_forecast_horizons_hours:
            target_time = reference + timedelta(hours=horizon_hours)
            trend = damped_trend_prediction(points, float(horizon_hours))
            predictions = {PERSISTENCE: last_value}
            if trend is not None:
                predictions[DAMPED_TREND] = _clamp(spec, trend)
            for model_name, predicted in predictions.items():
                session.add(
                    MetricForecast(
                        metric=spec.key,
                        model_name=model_name,
                        model_version=MODEL_VERSION,
                        made_at=reference,
                        target_time=target_time,
                        horizon_minutes=horizon_hours * 60,
                        predicted_value=predicted,
                    )
                )
                created += 1
    if created:
        await session.commit()
    return created


async def resolve_forecasts(
    session: AsyncSession, settings: Settings, now: datetime | None = None
) -> int:
    """Score matured forecasts against the nearest recorded observation."""
    reference = now or datetime.now(UTC)
    tolerance = timedelta(minutes=settings.learning_forecast_match_tolerance_minutes)
    due = (
        await session.scalars(
            select(MetricForecast).where(
                MetricForecast.resolved_at.is_(None),
                MetricForecast.target_time <= reference,
                MetricForecast.target_time >= reference - _RESOLVE_LOOKBACK,
            )
        )
    ).all()
    resolved = 0
    for forecast in due:
        target = forecast.target_time
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        rows = (
            await session.execute(
                select(MetricSample.time_tag, MetricSample.value).where(
                    MetricSample.metric == forecast.metric,
                    MetricSample.time_tag >= target - tolerance,
                    MetricSample.time_tag <= target + tolerance,
                )
            )
        ).all()
        if not rows:
            continue
        best: tuple[float, float] | None = None
        for tag, value in rows:
            if tag.tzinfo is None:
                tag = tag.replace(tzinfo=UTC)
            distance = abs((tag - target).total_seconds())
            if best is None or distance < best[0]:
                best = (distance, value)
        assert best is not None
        actual = best[1]
        forecast.actual_value = actual
        forecast.abs_error = abs(actual - forecast.predicted_value)
        forecast.resolved_at = reference
        resolved += 1
    if resolved:
        await session.commit()
    return resolved


async def forecast_skill(session: AsyncSession) -> list[ForecastSkill]:
    """Mean absolute error per metric/model/horizon, with the damped-trend
    error expressed relative to persistence (skill < 1 beats the control)."""
    rows = (
        await session.execute(
            select(
                MetricForecast.metric,
                MetricForecast.model_name,
                MetricForecast.horizon_minutes,
                func.count(MetricForecast.id),
                func.avg(MetricForecast.abs_error),
            )
            .where(MetricForecast.abs_error.is_not(None))
            .group_by(
                MetricForecast.metric, MetricForecast.model_name, MetricForecast.horizon_minutes
            )
        )
    ).all()
    persistence_error: dict[tuple[str, int], float] = {
        (metric, horizon): float(mean_error)
        for metric, model_name, horizon, _, mean_error in rows
        if model_name == PERSISTENCE and mean_error is not None
    }
    skill: list[ForecastSkill] = []
    for metric, model_name, horizon, count, mean_error in rows:
        if mean_error is None or metric not in METRICS_BY_KEY:
            continue
        baseline_error = persistence_error.get((metric, horizon))
        relative: float | None = None
        if model_name != PERSISTENCE and baseline_error:
            relative = float(mean_error) / baseline_error
        skill.append(
            ForecastSkill(
                metric=metric,
                model_name=model_name,
                horizon_minutes=horizon,
                resolved_count=int(count),
                mean_abs_error=float(mean_error),
                skill_vs_persistence=relative,
            )
        )
    skill.sort(key=lambda item: (item.metric, item.horizon_minutes, item.model_name))
    return skill
