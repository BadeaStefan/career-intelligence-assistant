"""Fit-analysis read/retry endpoints (Task 14).

Handlers stay thin: querying, grouping-by-verdict, and serialisation live in
``analysis/service.py``. This module only translates results into HTTP
status codes -- the same shape as ``routes/documents.py``'s
``_require_document``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.analysis import service
from career_intel.api.schemas import AnalysisDetail, AnalysisSummary
from career_intel.db import get_session
from career_intel.models.analysis import FitAnalysis

router = APIRouter(prefix="/analyses", tags=["analyses"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[AnalysisSummary])
async def get_analyses(session: SessionDep) -> list[AnalysisSummary]:
    return await service.list_analyses(session)


@router.get("/{job_doc_id}", response_model=AnalysisDetail)
async def get_analysis(job_doc_id: uuid.UUID, session: SessionDep) -> AnalysisDetail:
    detail = await service.get_analysis_detail(session, job_doc_id)

    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No fit analysis for this job.")

    return detail


@router.post("/{job_doc_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_analysis(
    job_doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> None:
    analysis = await _require_failed_analysis(session, job_doc_id)

    # Flip to pending synchronously, before scheduling the background work --
    # this is what makes a concurrent GET reflect "analysing" immediately,
    # and what makes a second retry request in a row correctly see 409
    # instead of racing this one to 202.
    await service.reset_to_pending(session, analysis)

    background_tasks.add_task(
        service.run_fit_analysis_background,
        resume_doc_id=analysis.resume_doc_id,
        job_doc_id=analysis.job_doc_id,
    )


async def _require_failed_analysis(session: AsyncSession, job_doc_id: uuid.UUID) -> FitAnalysis:
    analysis = await service.get_analysis_row(session, job_doc_id)

    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No fit analysis for this job.")

    if analysis.status != "failed":
        # Recomputing a good (or already-running) analysis silently costs
        # money and can change verdicts -- both pending and ready are
        # refused, not just ready.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only a failed analysis can be retried."
        )

    return analysis
