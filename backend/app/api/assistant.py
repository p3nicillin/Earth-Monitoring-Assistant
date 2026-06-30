from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.api import (
    AssistantRequest,
    AssistantResponse,
    GeoJSONFeatureCollection,
)
from app.services.assistant import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantResponse)
async def query_assistant(
    payload: AssistantRequest, session: SessionDep, user: CurrentUser
) -> AssistantResponse:
    answer, intent, features = await AssistantService(session).answer(
        payload.question, user_id=user.id, project_id=payload.project_id
    )
    return AssistantResponse(
        answer=answer,
        interpreted_filters=intent.serializable(),
        result_count=len(features),
        features=GeoJSONFeatureCollection(features=features),
        suggestions=[
            "Show critical events this week",
            "Where is crop stress increasing?",
            "Show environmental changes this month",
        ],
    )
