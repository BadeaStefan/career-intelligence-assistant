"""Request-scoped telemetry endpoint for the trace drawer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.api.schemas import LlmCallTrace, RetrievalTraceSummary, TraceDetail
from career_intel.db import get_session
from career_intel.telemetry import service

router = APIRouter(prefix="/traces", tags=["traces"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{request_id}", response_model=TraceDetail)
async def get_traces(
    request_id: Annotated[str, Path(min_length=1, max_length=64)], session: SessionDep
) -> TraceDetail:
    calls, retrievals = await service.get_request_traces(session, request_id)
    return TraceDetail(
        llm_calls=[LlmCallTrace.model_validate(call) for call in calls],
        retrievals=[RetrievalTraceSummary.model_validate(row) for row in retrievals],
    )
