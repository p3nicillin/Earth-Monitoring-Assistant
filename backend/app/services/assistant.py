import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Event, EventCategory, Project, Severity

CATEGORY_TERMS: dict[EventCategory, tuple[str, ...]] = {
    EventCategory.environment: (
        "forest",
        "deforestation",
        "wildfire",
        "burn",
        "water",
        "ice",
        "snow",
        "environment",
    ),
    EventCategory.agriculture: ("crop", "farm", "field", "harvest", "irrigation", "yield"),
    EventCategory.urban: ("building", "construction", "urban", "road", "solar"),
    EventCategory.infrastructure: ("bridge", "pipeline", "dam", "port", "infrastructure"),
    EventCategory.disaster: ("flood", "earthquake", "storm", "damage", "disaster"),
    EventCategory.maritime: ("ship", "vessel", "fishing", "marine", "oil spill"),
}


@dataclass(frozen=True)
class AssistantIntent:
    category: EventCategory | None
    severity: Severity | None
    since: datetime | None
    event_terms: tuple[str, ...]

    def serializable(self) -> dict[str, Any]:
        return {
            "category": self.category.value if self.category else None,
            "severity": self.severity.value if self.severity else None,
            "since": self.since.isoformat() if self.since else None,
            "event_terms": list(self.event_terms),
        }


def interpret_question(question: str, *, now: datetime | None = None) -> AssistantIntent:
    text = question.lower()
    category = next(
        (
            category
            for category, terms in CATEGORY_TERMS.items()
            if any(term in text for term in terms)
        ),
        None,
    )
    severity = next(
        (level for level in Severity if re.search(rf"\b{level.value}\b", text)),
        None,
    )
    current = now or datetime.now(UTC)
    if "today" in text or "24 hour" in text:
        since = current - timedelta(hours=24)
    elif "week" in text or "7 day" in text:
        since = current - timedelta(days=7)
    elif "month" in text or "30 day" in text:
        since = current - timedelta(days=30)
    elif "year" in text:
        since = current - timedelta(days=365)
    else:
        since = None
    detected_terms = tuple(
        term
        for terms in CATEGORY_TERMS.values()
        for term in terms
        if len(term) > 4 and term in text
    )
    return AssistantIntent(category, severity, since, detected_terms)


class AssistantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def answer(
        self, question: str, *, user_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> tuple[str, AssistantIntent, list[dict[str, Any]]]:
        intent = interpret_question(question)
        filters: list[Any] = [Project.owner_id == user_id]
        if project_id:
            filters.append(Event.project_id == project_id)
        if intent.category:
            filters.append(Event.category == intent.category)
        if intent.severity:
            filters.append(Event.severity == intent.severity)
        if intent.since:
            filters.append(Event.detected_at >= intent.since)

        rows = (
            await self.session.execute(
                select(Event, ST_AsGeoJSON(Event.geometry))
                .join(Project)
                .where(*filters)
                .order_by(Event.detected_at.desc())
                .limit(100)
            )
        ).all()
        features = [
            {
                "type": "Feature",
                "id": str(event.id),
                "geometry": json.loads(geometry),
                "properties": {
                    "title": event.title,
                    "summary": event.summary,
                    "category": event.category.value,
                    "severity": event.severity.value,
                    "confidence": event.confidence,
                    "detectedAt": event.detected_at.isoformat(),
                },
            }
            for event, geometry in rows
        ]
        if not rows:
            answer = (
                "I found no matching detections in your authorised projects. "
                "Try a wider period or category."
            )
        else:
            categories = sorted({event.category.value for event, _ in rows})
            severe = sum(event.severity in (Severity.high, Severity.critical) for event, _ in rows)
            answer = (
                f"I found {len(rows)} matching detection{'s' if len(rows) != 1 else ''} across "
                f"{', '.join(categories)}. {severe} are high or critical severity. "
                "The map has been filtered to these results; open an event to inspect its evidence."
            )
        return answer, intent, features
