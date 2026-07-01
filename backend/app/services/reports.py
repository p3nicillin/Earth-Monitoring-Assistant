from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Event, Project, Report, User


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(
        self,
        *,
        project: Project,
        user: User,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Report:
        events = list(
            (
                await self.session.scalars(
                    select(Event)
                    .where(
                        Event.project_id == project.id,
                        Event.detected_at >= period_start,
                        Event.detected_at <= period_end,
                    )
                    .order_by(Event.detected_at.desc())
                )
            ).all()
        )
        categories = Counter(event.category.value for event in events)
        severities = Counter(event.severity.value for event in events)
        mean_confidence = (
            round(sum(event.confidence for event in events) / len(events), 3) if events else None
        )
        highlights = [
            {
                "event_id": str(event.id),
                "title": event.title,
                "severity": event.severity.value,
                "confidence": event.confidence,
                "detected_at": event.detected_at.isoformat(),
            }
            for event in events[:10]
        ]
        content = {
            "summary": (
                f"{len(events)} detections were recorded for {project.name} in the selected period."
            ),
            "event_count": len(events),
            "categories": dict(categories),
            "severities": dict(severities),
            "mean_confidence": mean_confidence,
            "reviewed_count": sum(event.is_reviewed for event in events),
            "highlights": highlights,
            "methodology": (
                "Counts include authorised project events in the selected UTC interval. "
                "Detections are indicators and require evidence review before "
                "operational decisions."
            ),
        }
        report = Report(
            project_id=project.id,
            created_by_id=user.id,
            title=f"{project.name} — {report_type.title()} report",
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            content=content,
        )
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report
