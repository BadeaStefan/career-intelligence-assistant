"""Interview-prep generation/read endpoints (Task 20).

Mirrors ``routes/analyses.py``'s thin-handler shape: this module only
resolves ``job_doc_id`` -> the ``FitAnalysis`` it belongs to, translates
status into HTTP codes, and serialises -- generation, validation, and
persistence all live in ``prep/service.py``.

Generation is a POST, reading is a GET (spec §7): a generating GET would be
non-idempotent -- TanStack Query's refetch-on-focus or a double-click would
fire two concurrent generations that race the ``UNIQUE(fit_analysis_id)``
constraint and bill two LLM calls. The POST handles that race itself
(``prep/service.py``'s ``generate_prep``, via ``ON CONFLICT (fit_analysis_id)
DO NOTHING``) and always returns the single surviving row.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.analysis import service as analysis_service
from career_intel.api.schemas import PrepDetail
from career_intel.config import get_settings
from career_intel.db import get_session, get_session_factory
from career_intel.llm.openai_client import OpenAIClient
from career_intel.models.analysis import FitAnalysis
from career_intel.prep import service

router = APIRouter(prefix="/prep", tags=["prep"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/{job_doc_id}", response_model=PrepDetail)
async def post_prep(job_doc_id: uuid.UUID, session: SessionDep) -> PrepDetail:
    analysis = await _require_ready_analysis(session, job_doc_id)

    # Built fresh per request, from settings -- OpenAIClient builds its raw
    # SDK client lazily on first real call, so constructing it here makes no
    # network call by itself (same convention as routes/chat.py).
    llm = OpenAIClient(session_factory=get_session_factory(), settings=get_settings())
    await service.get_or_generate_prep(session, fit_analysis_id=analysis.id, llm=llm)

    detail = await service.get_prep_detail(session, job_doc_id)
    if detail is None:
        # Cannot happen: get_or_generate_prep above either returned an
        # existing row or just created one for this exact job_doc_id.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prep generation did not persist."
        )
    return detail


@router.get("/{job_doc_id}", response_model=PrepDetail)
async def get_prep(job_doc_id: uuid.UUID, session: SessionDep) -> PrepDetail:
    """Read-only: never generates. 404 until a POST has produced a row."""
    detail = await service.get_prep_detail(session, job_doc_id)

    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No interview prep for this job yet.")

    return detail


async def _require_ready_analysis(session: AsyncSession, job_doc_id: uuid.UUID) -> FitAnalysis:
    analysis = await analysis_service.get_analysis_row(session, job_doc_id)

    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No fit analysis for this job.")

    if analysis.status != "ready":
        # Generating from a pending or failed analysis would derive
        # questions from nothing (or from stale/absent verdicts).
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Fit analysis is not ready yet."
        )

    return analysis
