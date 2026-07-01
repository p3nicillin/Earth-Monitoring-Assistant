from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.api import EventReview, GeoJSONPolygon, ReportCreate, UserCreate


def test_polygon_must_be_closed() -> None:
    with pytest.raises(ValidationError, match="closed"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[[[0, 0], [1, 0], [1, 1], [0, 1]]],
        )


def test_registration_requires_strong_password() -> None:
    with pytest.raises(ValidationError, match="upper and lower"):
        UserCreate(email="person@example.com", display_name="Person", password="alllowercase123")


def test_polygon_must_be_topologically_valid() -> None:
    with pytest.raises(ValidationError, match="topologically valid"):
        GeoJSONPolygon(
            type="Polygon",
            coordinates=[[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
        )


def test_report_period_must_be_chronological() -> None:
    instant = datetime(2026, 6, 30, tzinfo=UTC)
    with pytest.raises(ValidationError, match="period_end"):
        ReportCreate(
            project_id="7e94c166-b673-4022-a9b3-a43652cf271e",
            period_start=instant,
            period_end=instant,
        )


def test_review_requires_a_decision() -> None:
    with pytest.raises(ValidationError):
        EventReview(outcome="unreviewed")  # type: ignore[arg-type]
