"""Queries backing the trace drawer.

The write paths live beside the operations they observe. This module is only
the safe read boundary: it returns telemetry rows already scoped to one
request id and never joins documents, chunks, or evidence text.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.models import LlmCall, RetrievalTrace


async def get_request_traces(
    session: AsyncSession, request_id: str
) -> tuple[list[LlmCall], list[RetrievalTrace]]:
    calls = list(
        (
            await session.execute(
                select(LlmCall)
                .where(LlmCall.request_id == request_id)
                .order_by(LlmCall.created_at, LlmCall.id)
            )
        )
        .scalars()
        .all()
    )
    retrievals = list(
        (
            await session.execute(
                select(RetrievalTrace)
                .where(RetrievalTrace.request_id == request_id)
                .order_by(RetrievalTrace.created_at, RetrievalTrace.id)
            )
        )
        .scalars()
        .all()
    )
    return calls, retrievals
