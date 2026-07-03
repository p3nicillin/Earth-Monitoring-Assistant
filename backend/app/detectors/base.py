"""Detector extension point.

A detector consumes a watch area's already-persisted observations and returns
evidence-backed DetectionResults; it never touches the database session
itself. MonitoringService (app/services/monitoring.py) is the only place that
turns a flagged DetectionResult into a persisted Event, keeping "observations
always persist, events are optional and evidence-backed" enforced in one spot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings
from app.models.entities import EventCategory, Observation, Severity, WatchArea


@dataclass(frozen=True)
class DetectorContext:
    watch_area: WatchArea
    geometry: dict[str, Any]
    observations: list[Observation]
    settings: Settings


@dataclass(frozen=True)
class DetectionResult:
    flagged: bool
    title: str
    summary: str
    event_type: str
    category: EventCategory
    severity: Severity
    confidence: float
    geometry: dict[str, Any]
    area_sq_km: float | None
    evidence: dict[str, Any]
    observation_id: uuid.UUID


class Detector(Protocol):
    name: str
    version: str

    async def detect(self, context: DetectorContext) -> list[DetectionResult]: ...
