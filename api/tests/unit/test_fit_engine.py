"""Tests for the fit-analysis engine (Task 13).

Embeddings are hand-built one-hot-ish vectors, mirroring test_retrieval.py --
a hash-based FakeEmbedder vector gives no control over which evidence unit
ends up nearest a given requirement, and several of these tests care about
which candidates get offered.
"""

import asyncio
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from career_intel.analysis.engine import run_fit_analysis, schedule_fit_analyses
from career_intel.constants import EMBEDDING_DIM
from career_intel.db import get_session_factory
from career_intel.llm.fakes import FakeLLM
from career_intel.llm.protocol import LLMClient, T
from career_intel.models import Document, EvidenceUnit, Requirement
from career_intel.models.analysis import FitAnalysis, RequirementMatch


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


async def _seed_ready_resume(session: AsyncSession, *, evidence_count: int = 3) -> Document:
    resume = Document(
        kind="resume", source="paste", raw_text="resume", status="ready", extraction_status="ready"
    )
    session.add(resume)
    await session.flush()

    for i in range(evidence_count):
        session.add(
            EvidenceUnit(
                document_id=resume.id,
                kind="skill",
                text=f"evidence {i}",
                char_start=None,
                char_end=None,
                embedding=_vector(i),
            )
        )
    await session.commit()
    await session.refresh(resume)
    return resume


async def _seed_job(session: AsyncSession, *, extraction_status: str = "ready") -> Document:
    job = Document(
        kind="job",
        source="paste",
        raw_text="job",
        status="ready",
        extraction_status=extraction_status,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _seed_job_with_requirements(session: AsyncSession, *, count: int) -> Document:
    job = await _seed_job(session)
    for i in range(count):
        session.add(
            Requirement(
                document_id=job.id,
                ordinal=i,
                text=f"requirement {i}",
                importance="required" if i % 2 == 0 else "preferred",
                category="general",
                embedding=_vector(i),
            )
        )
    await session.commit()
    await session.refresh(job)
    return job


async def _seed_analysis(
    session: AsyncSession,
    *,
    resume_doc_id: UUID | None = None,
    job_doc_id: UUID | None = None,
    status: str = "pending",
) -> FitAnalysis:
    if resume_doc_id is None:
        resume_doc_id = (await _seed_ready_resume(session)).id
    if job_doc_id is None:
        job_doc_id = (await _seed_job(session)).id
    analysis = FitAnalysis(
        resume_doc_id=resume_doc_id,
        job_doc_id=job_doc_id,
        status=status,
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis


async def _reload(analysis: FitAnalysis) -> FitAnalysis:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(FitAnalysis)
            .options(selectinload(FitAnalysis.matches).selectinload(RequirementMatch.evidence))
            .where(FitAnalysis.id == analysis.id)
        )
        return result.scalar_one()


def _verdict_payload(
    handle: str, *, verdict: str = "strong", evidence_handles: list[str] | None = None
) -> dict[str, Any]:
    return {
        "requirement_handle": handle,
        "verdict": verdict,
        "rationale": "matches",
        "evidence_handles": evidence_handles or [],
    }


def _batch_response(handles: list[str], **kwargs: Any) -> dict[str, Any]:
    return {"verdicts": [_verdict_payload(h, **kwargs) for h in handles]}


class _ExplodingLLM:
    """Satisfies LLMClient; always raises. No queued state needed."""

    async def structured(self, *, purpose: str, system: str, user: str, schema: type[T]) -> T:
        raise RuntimeError("boom")

    async def text(self, *, purpose: str, system: str, user: str) -> str:
        raise RuntimeError("boom")


@pytest.fixture
def exploding_llm() -> LLMClient:
    return _ExplodingLLM()


async def test_scores_every_requirement_not_just_retrieved_ones(session: AsyncSession) -> None:
    """Exhaustive coverage is the whole point: top-k retrieval would
    silently omit the requirement that mattered. Spec §1."""
    resume = await _seed_ready_resume(session)
    job = await _seed_job_with_requirements(session, count=14)
    fake_llm = FakeLLM(
        structured_responses=[
            _batch_response([f"r{i}" for i in range(1, 11)]),
            _batch_response([f"r{i}" for i in range(11, 15)]),
        ]
    )

    analysis = await run_fit_analysis(
        session, resume_doc_id=resume.id, job_doc_id=job.id, llm=fake_llm
    )

    assert len(analysis.matches) == 14


async def test_batches_large_jobs(session: AsyncSession) -> None:
    resume = await _seed_ready_resume(session)
    job = await _seed_job_with_requirements(session, count=25)
    fake_llm = FakeLLM(
        structured_responses=[
            _batch_response([f"r{i}" for i in range(1, 11)]),
            _batch_response([f"r{i}" for i in range(11, 21)]),
            _batch_response([f"r{i}" for i in range(21, 26)]),
        ]
    )

    await run_fit_analysis(session, resume_doc_id=resume.id, job_doc_id=job.id, llm=fake_llm)

    assert len(fake_llm.calls) == 3


async def test_invented_evidence_handles_are_not_persisted(session: AsyncSession) -> None:
    resume = await _seed_ready_resume(session, evidence_count=3)
    job = await _seed_job_with_requirements(session, count=2)

    offered_ids = set(
        (
            await session.execute(
                select(EvidenceUnit.id).where(EvidenceUnit.document_id == resume.id)
            )
        )
        .scalars()
        .all()
    )

    # lying_llm: cites "e99", which was never offered as a candidate for
    # either requirement (each only ever gets e1..e3 -- 3 evidence units).
    lying_llm = FakeLLM(
        structured_responses=[_batch_response(["r1", "r2"], evidence_handles=["e1", "e99"])]
    )

    analysis = await run_fit_analysis(
        session, resume_doc_id=resume.id, job_doc_id=job.id, llm=lying_llm
    )

    persisted = {e.evidence_unit_id for m in analysis.matches for e in m.evidence}
    assert persisted, "the valid handle e1 should still have been persisted"
    assert all(eid in offered_ids for eid in persisted)


async def test_failure_marks_analysis_failed_not_pending(
    session: AsyncSession, exploding_llm: LLMClient
) -> None:
    resume = await _seed_ready_resume(session)
    job = await _seed_job_with_requirements(session, count=2)
    analysis = await _seed_analysis(
        session, resume_doc_id=resume.id, job_doc_id=job.id, status="pending"
    )

    with pytest.raises(RuntimeError):
        await run_fit_analysis(
            session, resume_doc_id=resume.id, job_doc_id=job.id, llm=exploding_llm
        )

    reloaded = await _reload(analysis)
    assert reloaded.status == "failed"


async def test_concurrent_scheduling_claims_each_pair_once(session_factory: Any) -> None:
    """A resume and a job can finish enrichment at nearly the same moment;
    each background task sees the pair as newly complete. ON CONFLICT
    DO NOTHING plus compute-only-what-you-claimed prevents double work."""
    async with session_factory() as seed_session:
        await _seed_ready_resume(seed_session)
        await _seed_job(seed_session)

    async with session_factory() as s1, session_factory() as s2:
        claimed = await asyncio.gather(schedule_fit_analyses(s1), schedule_fit_analyses(s2))

    assert sorted(len(c) for c in claimed) == [0, 1]


async def test_extraction_failed_job_is_never_scheduled(session: AsyncSession) -> None:
    """A job that degraded to chunk RAG has zero requirements; an analysis
    over it would be a confidently empty verdict. Spec §3: such a job is
    answerable in chat but cannot produce a fit analysis."""
    await _seed_ready_resume(session)
    await _seed_job(session, extraction_status="failed")

    assert await schedule_fit_analyses(session) == []
