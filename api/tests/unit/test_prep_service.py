"""Tests for interview-prep generation (Task 20).

Mirrors test_fit_engine.py's inline-construction style: Document,
Requirement, FitAnalysis, RequirementMatch, MatchEvidence, and EvidenceUnit
rows are built directly via the ORM inside each test, no shared fixtures
beyond the ``session`` fixture in conftest.py.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from career_intel.constants import EMBEDDING_DIM
from career_intel.llm.fakes import FakeLLM
from career_intel.models import Document, EvidenceUnit, Requirement
from career_intel.models.analysis import FitAnalysis, MatchEvidence, RequirementMatch
from career_intel.prep.service import generate_prep, get_or_generate_prep


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


async def _seed_ready_resume(
    session: AsyncSession, *, evidence_count: int = 3
) -> tuple[Document, list[EvidenceUnit]]:
    resume = Document(
        kind="resume", source="paste", raw_text="resume", status="ready", extraction_status="ready"
    )
    session.add(resume)
    await session.flush()

    units = [
        EvidenceUnit(
            document_id=resume.id,
            kind="skill",
            text=f"evidence {i}",
            char_start=None,
            char_end=None,
            embedding=_vector(i),
        )
        for i in range(evidence_count)
    ]
    session.add_all(units)
    await session.flush()
    return resume, units


async def _seed_job_with_requirements(
    session: AsyncSession, *, count: int
) -> tuple[Document, list[Requirement]]:
    job = Document(
        kind="job", source="paste", raw_text="job", status="ready", extraction_status="ready"
    )
    session.add(job)
    await session.flush()

    requirements = [
        Requirement(
            document_id=job.id,
            ordinal=i,
            text=f"requirement {i}",
            importance="required" if i % 2 == 0 else "preferred",
            category="general",
            embedding=_vector(i + 10),
        )
        for i in range(count)
    ]
    session.add_all(requirements)
    await session.flush()
    return job, requirements


async def _seed_ready_analysis(
    session: AsyncSession,
    *,
    requirement_count: int = 2,
    evidence_count: int = 3,
    verdict: str = "partial",
    link_all_evidence_to_each: bool = False,
) -> tuple[FitAnalysis, list[Requirement], list[EvidenceUnit]]:
    """A ready fit analysis with one RequirementMatch per requirement.

    ``link_all_evidence_to_each=False`` (the default) gives each
    requirement's match a disjoint slice of the evidence pool (cycling
    through it), which is what the cross-requirement-leak test below needs:
    r1's and r2's offered evidence handles must not overlap for that test to
    prove anything.
    """
    resume, evidence_units = await _seed_ready_resume(session, evidence_count=evidence_count)
    job, requirements = await _seed_job_with_requirements(session, count=requirement_count)
    analysis = FitAnalysis(
        resume_doc_id=resume.id,
        job_doc_id=job.id,
        status="ready",
        overall_score=0.6,
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.flush()

    for index, requirement in enumerate(requirements):
        match = RequirementMatch(
            fit_analysis_id=analysis.id,
            requirement_id=requirement.id,
            verdict=verdict,
            rationale=f"rationale {index}",
        )
        session.add(match)
        await session.flush()

        linked = (
            evidence_units
            if link_all_evidence_to_each
            else [evidence_units[index % len(evidence_units)]]
        )
        for unit in linked:
            session.add(MatchEvidence(requirement_match_id=match.id, evidence_unit_id=unit.id))

    await session.commit()

    result = await session.execute(
        select(FitAnalysis)
        .options(selectinload(FitAnalysis.matches).selectinload(RequirementMatch.evidence))
        .where(FitAnalysis.id == analysis.id)
    )
    return result.scalar_one(), requirements, evidence_units


def _question_payload(
    handle: str, *, evidence_handles: list[str] | None = None, question: str | None = None
) -> dict[str, Any]:
    return {
        "question": question or f"Tell me more about {handle}.",
        "probes_requirement_handle": handle,
        "why_they_will_ask": "It probes a gap the verdict identified.",
        "how_to_frame": "Acknowledge the gap, then bridge from adjacent experience.",
        "evidence_handles": evidence_handles or [],
    }


def _prep_batch_response(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    return {"questions": payloads}


async def test_generates_five_to_eight_questions_anchored_to_real_requirements(
    session: AsyncSession,
) -> None:
    analysis, requirements, _evidence_units = await _seed_ready_analysis(
        session, requirement_count=6, evidence_count=3
    )
    fake_llm = FakeLLM(
        structured_responses=[
            _prep_batch_response([_question_payload(f"r{i}") for i in range(1, 7)])
        ]
    )

    prep = await generate_prep(session, fit_analysis_id=analysis.id, llm=fake_llm)

    assert 5 <= len(prep.questions) <= 8
    requirement_ids = {r.id for r in requirements}
    assert all(q.requirement_id in requirement_ids for q in prep.questions)


async def test_invented_evidence_handles_are_dropped(session: AsyncSession) -> None:
    analysis, _requirements, evidence_units = await _seed_ready_analysis(
        session, requirement_count=2, evidence_count=1, link_all_evidence_to_each=True
    )
    offered_evidence_ids = {unit.id for unit in evidence_units}

    # lying_llm cites "e99", never offered for either requirement, alongside
    # the genuinely-offered "r1e1".
    lying_llm = FakeLLM(
        structured_responses=[
            _prep_batch_response(
                [
                    _question_payload("r1", evidence_handles=["r1e1", "e99"]),
                    _question_payload("r2", evidence_handles=["bogus"]),
                    _question_payload("r1"),
                    _question_payload("r2"),
                    _question_payload("r1"),
                ]
            )
        ]
    )

    prep = await generate_prep(session, fit_analysis_id=analysis.id, llm=lying_llm)

    persisted = {eid for q in prep.questions for eid in q.evidence_ids}
    assert persisted, "the valid handle r1e1 should still have been persisted"
    assert persisted <= offered_evidence_ids


async def test_cross_requirement_evidence_handle_leak_is_dropped(session: AsyncSession) -> None:
    """r1's evidence handles and r2's evidence handles must not resolve
    across requirements, even though both are structurally well-formed
    handles that were genuinely offered -- just for the other requirement
    (non-negotiable #6/#7, mirrors test_fit_engine.py's own collision test)."""
    analysis, _requirements, _evidence_units = await _seed_ready_analysis(
        session, requirement_count=2, evidence_count=2, link_all_evidence_to_each=False
    )
    fake_llm = FakeLLM(
        structured_responses=[
            _prep_batch_response(
                [
                    _question_payload("r1", evidence_handles=["r2e1"]),
                    _question_payload("r2", evidence_handles=["r1e1"]),
                ]
            )
        ]
    )

    prep = await generate_prep(session, fit_analysis_id=analysis.id, llm=fake_llm)

    assert len(prep.questions) == 2
    for question in prep.questions:
        assert question.evidence_ids == [], "a cross-requirement handle must never validate"


async def test_requirement_handle_never_offered_is_dropped(session: AsyncSession) -> None:
    analysis, _requirements, _evidence_units = await _seed_ready_analysis(
        session, requirement_count=2
    )
    fake_llm = FakeLLM(
        structured_responses=[
            _prep_batch_response(
                [_question_payload("r1"), _question_payload("r99")]  # r99 was never offered
            )
        ]
    )

    prep = await generate_prep(session, fit_analysis_id=analysis.id, llm=fake_llm)

    assert len(prep.questions) == 1
    assert prep.questions[0].question == "Tell me more about r1."


async def test_requirement_with_no_linked_evidence_is_still_offered(session: AsyncSession) -> None:
    """A requirement whose match has no linked evidence still gets a handle
    (as "no evidence") so the model can still ask about the verdict --
    it just cannot cite anything for it."""
    resume, _evidence_units = await _seed_ready_resume(session, evidence_count=0)
    job, requirements = await _seed_job_with_requirements(session, count=1)
    analysis = FitAnalysis(
        resume_doc_id=resume.id,
        job_doc_id=job.id,
        status="ready",
        overall_score=0.0,
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.flush()
    session.add(
        RequirementMatch(
            fit_analysis_id=analysis.id,
            requirement_id=requirements[0].id,
            verdict="missing",
            rationale="no evidence found",
        )
    )
    await session.commit()

    fake_llm = FakeLLM(structured_responses=[_prep_batch_response([_question_payload("r1")])])

    prep = await generate_prep(session, fit_analysis_id=analysis.id, llm=fake_llm)

    assert len(prep.questions) == 1
    assert prep.questions[0].evidence_ids == []


async def test_second_generate_call_returns_cached_row_without_second_llm_call(
    session_factory: Any,
) -> None:
    async with session_factory() as seed_session:
        analysis, _requirements, _evidence_units = await _seed_ready_analysis(
            seed_session, requirement_count=2
        )
        fit_analysis_id = analysis.id

    fake_llm = FakeLLM(
        structured_responses=[
            _prep_batch_response([_question_payload("r1"), _question_payload("r2")])
        ]
    )

    async with session_factory() as first_session:
        first = await get_or_generate_prep(
            first_session, fit_analysis_id=fit_analysis_id, llm=fake_llm
        )

    async with session_factory() as second_session:
        second = await get_or_generate_prep(
            second_session, fit_analysis_id=fit_analysis_id, llm=fake_llm
        )

    assert second.id == first.id
    assert fake_llm.call_count == 1
