"""Read/retry query and serialisation logic for fit analyses (Task 14).

``api/routes/analyses.py`` stays thin per CLAUDE.md non-negotiable #3: it
translates results from here into HTTP status codes, but never builds a
query or groups matches itself. The grouping-by-verdict transformation in
particular is not a passthrough of an ORM object, so this module returns
plain ``schemas`` instances rather than ORM rows for the detail view.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from career_intel.analysis.engine import run_fit_analysis
from career_intel.api.schemas import (
    AnalysisDetail,
    AnalysisSummary,
    EvidenceSummary,
    RequirementMatchSummary,
)
from career_intel.config import get_settings
from career_intel.db import get_session_factory
from career_intel.llm.openai_client import OpenAIClient
from career_intel.llm.protocol import LLMClient
from career_intel.models import Document
from career_intel.models.analysis import FitAnalysis, RequirementMatch
from career_intel.models.evidence import EvidenceUnit

# Matches are presented strong, then partial, then missing -- the "grouped"
# breakdown the brief asks for, without splitting one list into three keys.
_VERDICT_ORDER = {"strong": 0, "partial": 1, "missing": 2}


async def list_analyses(session: AsyncSession) -> list[AnalysisSummary]:
    """The job rail: one row per job that Task 13's scheduler has claimed.

    A job whose extraction failed was never scheduled and has no
    ``fit_analyses`` row -- it correctly does not appear here. Its "no fit
    analysis" UI state is driven by ``Document.extraction_status``, a
    different endpoint's concern.
    """
    rows = (
        await session.execute(
            select(FitAnalysis, Document)
            .join(Document, Document.id == FitAnalysis.job_doc_id)
            .order_by(Document.created_at.desc())
        )
    ).all()

    return [
        AnalysisSummary(
            job_doc_id=analysis.job_doc_id,
            title=document.title,
            company=document.company,
            status=analysis.status,
            overall_score=analysis.overall_score,
        )
        for analysis, document in rows
    ]


async def get_analysis_detail(
    session: AsyncSession, job_doc_id: uuid.UUID
) -> AnalysisDetail | None:
    """The full breakdown for one job, or ``None`` if no row was ever claimed.

    This project assumes one resume at a time (spec: "ingests one resume and
    several job postings"), so no disambiguation by resume is needed --
    ``job_doc_id`` alone identifies the analysis.
    """
    analysis = await _load_analysis_with_matches(session, job_doc_id)
    if analysis is None:
        return None

    evidence_unit_ids = {
        evidence.evidence_unit_id for match in analysis.matches for evidence in match.evidence
    }
    evidence_units: dict[uuid.UUID, EvidenceUnit] = {}
    if evidence_unit_ids:
        unit_rows = (
            await session.execute(
                select(EvidenceUnit).where(EvidenceUnit.id.in_(evidence_unit_ids))
            )
        ).scalars()
        evidence_units = {unit.id: unit for unit in unit_rows}

    ordered_matches = sorted(analysis.matches, key=lambda m: _VERDICT_ORDER[m.verdict])

    return AnalysisDetail(
        job_doc_id=analysis.job_doc_id,
        status=analysis.status,
        overall_score=analysis.overall_score,
        matches=[
            RequirementMatchSummary(
                verdict=match.verdict,
                rationale=match.rationale,
                evidence=[
                    EvidenceSummary(
                        text=evidence_units[evidence.evidence_unit_id].text,
                        char_start=evidence_units[evidence.evidence_unit_id].char_start,
                        char_end=evidence_units[evidence.evidence_unit_id].char_end,
                    )
                    for evidence in match.evidence
                    # Defensive: a match_evidence row whose evidence_unit_id
                    # cannot be resolved is skipped rather than raising --
                    # should never happen given the FK, but this is a read
                    # path, not the place to turn a data anomaly into a 500.
                    if evidence.evidence_unit_id in evidence_units
                ],
            )
            for match in ordered_matches
        ],
    )


async def get_analysis_row(session: AsyncSession, job_doc_id: uuid.UUID) -> FitAnalysis | None:
    """The bare row, for the retry endpoint's status check."""
    result = await session.execute(
        select(FitAnalysis).where(FitAnalysis.job_doc_id == job_doc_id)
    )
    return result.scalars().first()


async def reset_to_pending(session: AsyncSession, analysis: FitAnalysis) -> None:
    """Flip the row back to ``pending`` synchronously, before any background
    work is scheduled.

    This is what keeps a concurrent ``GET`` reflecting "analysing"
    immediately, and what makes the 409-vs-202 check correct if retry is
    called twice in a row -- the second call sees ``pending``, not the stale
    ``failed`` it raced against. The retry request itself does no LLM work,
    so this commit is the only write it makes; run_fit_analysis's own
    session, opened later in the background task, is a separate one.
    """
    analysis.status = "pending"
    await session.commit()


async def run_fit_analysis_background(
    *, resume_doc_id: uuid.UUID, job_doc_id: uuid.UUID, llm: LLMClient | None = None
) -> None:
    """The retry endpoint's background task.

    Mirrors ``ingest/pipeline.py``'s ``enrich_document``: ``llm`` defaults to
    ``None``, meaning "build the real client from settings" so production
    retries actually call OpenAI, while tests inject a fake or monkeypatch
    this function out entirely (see ``test_analyses_route.py``'s autouse
    fixture). A fresh session is opened here rather than reusing the
    request's -- that session is closed by the time a background task runs.
    """
    session_factory: async_sessionmaker[AsyncSession] = get_session_factory()

    if llm is None:
        llm = OpenAIClient(session_factory=session_factory, settings=get_settings())

    async with session_factory() as session:
        await run_fit_analysis(
            session, resume_doc_id=resume_doc_id, job_doc_id=job_doc_id, llm=llm
        )


async def _load_analysis_with_matches(
    session: AsyncSession, job_doc_id: uuid.UUID
) -> FitAnalysis | None:
    result = await session.execute(
        select(FitAnalysis)
        .options(selectinload(FitAnalysis.matches).selectinload(RequirementMatch.evidence))
        .where(FitAnalysis.job_doc_id == job_doc_id)
    )
    return result.scalars().first()
