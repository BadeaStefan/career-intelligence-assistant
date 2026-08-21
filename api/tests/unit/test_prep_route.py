"""Tests for the interview-prep HTTP surface (Task 20).

Mirrors test_analyses_route.py: seeding happens on a throwaway
engine/session, never the ``session`` fixture's cached one, because these
tests also drive ``client`` (a ``TestClient`` running the app in its own
thread with its own event loop) -- reusing the shared engine's connection
across event loops is exactly what conftest.py's ``_clean_tables`` fixture
exists to avoid.

``routes/prep.py`` builds a real ``OpenAIClient`` per request (same
convention as ``routes/chat.py``); the autouse fixture below monkeypatches
that class reference so every request gets the test's ``FakeLLM`` instead,
the same "stub the network boundary" shape test_analyses_route.py already
uses for the retry endpoint's background task.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_intel.constants import EMBEDDING_DIM
from career_intel.llm.fakes import FakeLLM
from career_intel.models import Document, EvidenceUnit, Requirement
from career_intel.models.analysis import FitAnalysis, MatchEvidence, RequirementMatch
from tests.conftest import TEST_DATABASE_URL

MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM(
        structured_responses=[
            {
                "questions": [
                    {
                        "question": "Tell me about your experience with requirement 0.",
                        "probes_requirement_handle": "r1",
                        "why_they_will_ask": "It's a required skill with a partial verdict.",
                        "how_to_frame": "Lead with the closest transferable experience.",
                        "evidence_handles": [],
                    },
                    {
                        "question": "Tell me about your experience with requirement 1.",
                        "probes_requirement_handle": "r2",
                        "why_they_will_ask": "It's a preferred skill with a partial verdict.",
                        "how_to_frame": "Lead with the closest transferable experience.",
                        "evidence_handles": [],
                    },
                ]
            }
        ]
    )


@pytest.fixture(autouse=True)
def _stub_openai_client(monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM) -> None:
    monkeypatch.setattr("career_intel.api.routes.prep.OpenAIClient", lambda **kwargs: fake_llm)


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


@asynccontextmanager
async def _throwaway_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _seed_resume(session: AsyncSession) -> tuple[Document, list[EvidenceUnit]]:
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
            char_start=0 if i == 0 else None,
            char_end=20 if i == 0 else None,
            embedding=_vector(i),
        )
        for i in range(2)
    ]
    session.add_all(units)
    await session.flush()
    return resume, units


async def _seed_job(session: AsyncSession) -> tuple[Document, list[Requirement]]:
    job = Document(
        kind="job",
        source="paste",
        raw_text="job",
        status="ready",
        extraction_status="ready",
        title="Senior Backend Engineer",
        company="Acme",
    )
    session.add(job)
    await session.flush()

    requirements = [
        Requirement(
            document_id=job.id,
            ordinal=i,
            text=f"requirement {i}",
            importance="required" if i == 0 else "preferred",
            category="general",
            embedding=_vector(i + 10),
        )
        for i in range(2)
    ]
    session.add_all(requirements)
    await session.flush()
    return job, requirements


@pytest_asyncio.fixture
async def pending_analysis() -> FitAnalysis:
    async with _throwaway_session() as session:
        resume, _ = await _seed_resume(session)
        job, _ = await _seed_job(session)
        analysis = FitAnalysis(
            resume_doc_id=resume.id, job_doc_id=job.id, status="pending", model="gpt-4o-mini"
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
        return analysis


@pytest_asyncio.fixture
async def ready_analysis() -> FitAnalysis:
    async with _throwaway_session() as session:
        resume, evidence_units = await _seed_resume(session)
        job, requirements = await _seed_job(session)
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
                verdict="partial",
                rationale=f"rationale {index}",
            )
            session.add(match)
            await session.flush()
            session.add(
                MatchEvidence(
                    requirement_match_id=match.id,
                    evidence_unit_id=evidence_units[index % len(evidence_units)].id,
                )
            )

        await session.commit()
        await session.refresh(analysis)
        return analysis


def test_second_post_returns_cached_row_without_second_llm_call(
    client: TestClient, fake_llm: FakeLLM, ready_analysis: FitAnalysis
) -> None:
    first = client.post(f"/prep/{ready_analysis.job_doc_id}")
    assert first.status_code == 200
    second = client.post(f"/prep/{ready_analysis.job_doc_id}")
    assert second.status_code == 200

    assert second.json() == first.json()
    assert fake_llm.call_count == 1


def test_post_response_carries_requirement_and_verdict_identity(
    client: TestClient, ready_analysis: FitAnalysis
) -> None:
    body = client.post(f"/prep/{ready_analysis.job_doc_id}").json()

    assert body["job_doc_id"] == str(ready_analysis.job_doc_id)
    assert len(body["questions"]) == 2
    for question in body["questions"]:
        assert question["verdict"] == "partial"
        assert question["requirement_text"]


def test_post_for_pending_analysis_returns_409(
    client: TestClient, pending_analysis: FitAnalysis
) -> None:
    # Generating from a pending analysis would derive questions from nothing.
    assert client.post(f"/prep/{pending_analysis.job_doc_id}").status_code == 409


def test_post_for_unscheduled_job_returns_404(client: TestClient) -> None:
    assert client.post(f"/prep/{MISSING_ID}").status_code == 404


def test_get_before_generation_returns_404(client: TestClient, ready_analysis: FitAnalysis) -> None:
    assert client.get(f"/prep/{ready_analysis.job_doc_id}").status_code == 404


def test_get_after_generation_returns_the_generated_detail(
    client: TestClient, ready_analysis: FitAnalysis
) -> None:
    posted = client.post(f"/prep/{ready_analysis.job_doc_id}").json()
    got = client.get(f"/prep/{ready_analysis.job_doc_id}")

    assert got.status_code == 200
    assert got.json() == posted
