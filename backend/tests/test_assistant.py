from datetime import UTC, datetime

from app.models.entities import EventCategory, Severity
from app.services.assistant import interpret_question


def test_interprets_category_severity_and_period() -> None:
    now = datetime(2026, 6, 30, 12, tzinfo=UTC)
    intent = interpret_question("Show critical wildfire events this week", now=now)
    assert intent.category == EventCategory.environment
    assert intent.severity == Severity.critical
    assert intent.since == datetime(2026, 6, 23, 12, tzinfo=UTC)


def test_unknown_question_does_not_invent_filters() -> None:
    intent = interpret_question("What changed here?")
    assert intent.category is None
    assert intent.severity is None
    assert intent.since is None
