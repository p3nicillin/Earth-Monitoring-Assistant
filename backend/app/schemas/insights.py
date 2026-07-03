"""API contracts for the adaptive-learning insights surface."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Direction = Literal["high", "low"]


class MetricBaseline(BaseModel):
    metric: str
    title: str
    unit: str
    direction: Direction
    sample_count: int
    window_days: int
    first_sample_at: datetime | None
    last_sample_at: datetime | None
    mean: float | None
    p50: float | None
    p95: float | None
    p99: float | None
    observed_extreme: float | None
    published_floor: float
    adaptive_threshold: float | None
    # 0..1: how far the archive is toward the configured minimum sample depth.
    maturity: float


class ForecastPoint(BaseModel):
    metric: str
    model_name: str
    model_version: str
    made_at: datetime
    target_time: datetime
    horizon_minutes: int
    predicted_value: float
    actual_value: float | None
    abs_error: float | None


class ForecastSkill(BaseModel):
    metric: str
    model_name: str
    horizon_minutes: int
    resolved_count: int
    mean_abs_error: float
    # < 1.0 means the model beats naive persistence at this horizon.
    skill_vs_persistence: float | None


class MetricArchiveStatus(BaseModel):
    metric: str
    title: str
    sample_count: int
    first_sample_at: datetime | None
    last_sample_at: datetime | None


class LearningStatus(BaseModel):
    generated_at: datetime
    learning_enabled: bool
    interval_seconds: int
    baseline_window_days: int
    min_baseline_samples: int
    archive: list[MetricArchiveStatus]
    total_samples: int
    forecasts_pending: int
    forecasts_resolved: int
    skill: list[ForecastSkill]


class ForecastFeed(BaseModel):
    generated_at: datetime
    upcoming: list[ForecastPoint]
    recent_resolved: list[ForecastPoint]
