"""Read-only surface over the adaptive-learning layer: archive depth,
learned baselines, forecasts, and measured forecast skill."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.learning.baselines import compute_baselines
from app.learning.forecasts import forecast_skill
from app.learning.metrics import METRIC_SPECS
from app.models.entities import MetricForecast, MetricSample
from app.schemas.insights import (
    ForecastFeed,
    ForecastPoint,
    LearningStatus,
    MetricArchiveStatus,
    MetricBaseline,
)

router = APIRouter(prefix="/insights", tags=["adaptive learning"])

_FEED_LIMIT = 96


def _forecast_point(row: MetricForecast) -> ForecastPoint:
    return ForecastPoint(
        metric=row.metric,
        model_name=row.model_name,
        model_version=row.model_version,
        made_at=row.made_at,
        target_time=row.target_time,
        horizon_minutes=row.horizon_minutes,
        predicted_value=row.predicted_value,
        actual_value=row.actual_value,
        abs_error=row.abs_error,
    )


@router.get("/status", response_model=LearningStatus)
async def status(user: CurrentUser, session: SessionDep) -> LearningStatus:
    del user
    settings = get_settings()
    archive_rows = (
        await session.execute(
            select(
                MetricSample.metric,
                func.count(MetricSample.id),
                func.min(MetricSample.time_tag),
                func.max(MetricSample.time_tag),
            ).group_by(MetricSample.metric)
        )
    ).all()
    by_metric = {metric: (count, first, last) for metric, count, first, last in archive_rows}
    archive = [
        MetricArchiveStatus(
            metric=spec.key,
            title=spec.title,
            sample_count=by_metric.get(spec.key, (0, None, None))[0],
            first_sample_at=by_metric.get(spec.key, (0, None, None))[1],
            last_sample_at=by_metric.get(spec.key, (0, None, None))[2],
        )
        for spec in METRIC_SPECS
    ]
    pending = await session.scalar(
        select(func.count(MetricForecast.id)).where(MetricForecast.resolved_at.is_(None))
    )
    resolved = await session.scalar(
        select(func.count(MetricForecast.id)).where(MetricForecast.resolved_at.is_not(None))
    )
    return LearningStatus(
        generated_at=datetime.now(UTC),
        learning_enabled=settings.learning_enabled,
        interval_seconds=settings.learning_interval_seconds,
        baseline_window_days=settings.learning_baseline_window_days,
        min_baseline_samples=settings.learning_min_baseline_samples,
        archive=archive,
        total_samples=sum(item.sample_count for item in archive),
        forecasts_pending=int(pending or 0),
        forecasts_resolved=int(resolved or 0),
        skill=await forecast_skill(session),
    )


@router.get("/baselines", response_model=list[MetricBaseline])
async def baselines(user: CurrentUser, session: SessionDep) -> list[MetricBaseline]:
    del user
    return await compute_baselines(session, get_settings())


@router.get("/forecasts", response_model=ForecastFeed)
async def forecasts(user: CurrentUser, session: SessionDep) -> ForecastFeed:
    del user
    now = datetime.now(UTC)
    upcoming = (
        await session.scalars(
            select(MetricForecast)
            .where(MetricForecast.target_time >= now)
            .order_by(MetricForecast.target_time)
            .limit(_FEED_LIMIT)
        )
    ).all()
    recent = (
        await session.scalars(
            select(MetricForecast)
            .where(MetricForecast.resolved_at.is_not(None))
            .order_by(MetricForecast.target_time.desc())
            .limit(_FEED_LIMIT)
        )
    ).all()
    return ForecastFeed(
        generated_at=now,
        upcoming=[_forecast_point(row) for row in upcoming],
        recent_resolved=[_forecast_point(row) for row in recent],
    )
