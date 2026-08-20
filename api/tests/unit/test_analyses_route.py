"""Tests for the fit-analysis read/retry HTTP surface (Task 14).

Seeding happens on a throwaway engine/session, never the ``session`` fixture's
cached one: these tests also drive ``client`` (a ``TestClient`` running the
app in its own thread with its own event loop, per ``conftest.py``'s
``client`` fixture docstring), and a connection checked out from the shared
engine in *this* test's event loop would be reused -- across event loops --
the moment the client's request handling checks out a connection from that
same pool. Mirrors ``conftest.py``'s ``_clean_tables`` fixture, which solves
the identical problem for truncation.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_intel.constants import EMBEDDING_DIM
from career_intel.models import Document, EvidenceUnit, Requirement
from career_intel.models.analysis import FitAnalysis, MatchEvidence, RequirementMatch
from tests.conftest import TEST_DATABASE_URL

MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def _stub_retry_background_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the HTTP contract, not the retry itself.

    ``routes/analyses.py`` schedules ``service.run_fit_analysis_background``
    via ``BackgroundTasks.add_task``, which ``TestClient`` runs synchronously
    within the request -- stubbed here so a retry never builds a real
    ``OpenAIClient`` or reaches the network.
    """

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("career_intel.analysis.service.run_fit_analysis_background", _noop)


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
async def failed_analysis() -> FitAnalysis:
    async with _throwaway_session() as session:
        resume, _ = await _seed_resume(session)
        job, _ = await _seed_job(session)
        analysis = FitAnalysis(
            resume_doc_id=resume.id, job_doc_id=job.id, status="failed", model="gpt-4o-mini"
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
        return analysis


async def _seed_ready_analysis(session: AsyncSession) -> tuple[FitAnalysis, list[Requirement]]:
    resume, evidence_units = await _seed_resume(session)
    job, requirements = await _seed_job(session)
    analysis = FitAnalysis(
        resume_doc_id=resume.id,
        job_doc_id=job.id,
        status="ready",
        overall_score=0.75,
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.flush()

    strong_match = RequirementMatch(
        fit_analysis_id=analysis.id,
        requirement_id=requirements[0].id,
        verdict="strong",
        rationale="Directly matches years of Python experience.",
    )
    missing_match = RequirementMatch(
        fit_analysis_id=analysis.id,
        requirement_id=requirements[1].id,
        verdict="missing",
        rationale="No evidence of this skill was found.",
    )
    session.add_all([strong_match, missing_match])
    await session.flush()

    # evidence_units[0] has a non-null char_start/char_end -- the test
    # asserts at least one such citation is present.
    session.add(
        MatchEvidence(requirement_match_id=strong_match.id, evidence_unit_id=evidence_units[0].id)
    )
    await session.commit()
    await session.refresh(analysis)
    return analysis, requirements


@pytest_asyncio.fixture
async def ready_analysis() -> FitAnalysis:
    async with _throwaway_session() as session:
        analysis, _requirements = await _seed_ready_analysis(session)
        return analysis


@pytest_asyncio.fixture
async def ready_analysis_with_requirements() -> tuple[FitAnalysis, list[Requirement]]:
    async with _throwaway_session() as session:
        return await _seed_ready_analysis(session)


def test_pending_analysis_returns_status_not_404(
    client: TestClient, pending_analysis: FitAnalysis
) -> None:
    response = client.get(f"/analyses/{pending_analysis.job_doc_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["overall_score"] is None


def test_ready_analysis_returns_matches_with_citation_offsets(
    client: TestClient, ready_analysis: FitAnalysis
) -> None:
    body = client.get(f"/analyses/{ready_analysis.job_doc_id}").json()
    assert body["status"] == "ready"
    assert 0.0 <= body["overall_score"] <= 1.0
    evidence = [e for m in body["matches"] for e in m["evidence"]]
    assert any(e["char_start"] is not None for e in evidence)
    for match in body["matches"]:
        assert match["verdict"] in {"strong", "partial", "missing"}
        assert match["rationale"]


def test_ready_analysis_matches_carry_requirement_identity(
    client: TestClient,
    ready_analysis_with_requirements: tuple[FitAnalysis, list[Requirement]],
) -> None:
    """The frontend cannot render a requirement row without its own text and
    importance -- Task 14's response omitted these, this closes that gap."""
    analysis, requirements = ready_analysis_with_requirements
    body = client.get(f"/analyses/{analysis.job_doc_id}").json()

    expected = {
        str(requirement.id): (requirement.text, requirement.importance)
        for requirement in requirements
    }

    assert len(body["matches"]) == len(expected)
    for match in body["matches"]:
        assert match["requirement_id"] in expected
        expected_text, expected_importance = expected[match["requirement_id"]]
        assert match["requirement_text"] == expected_text
        assert match["requirement_importance"] == expected_importance


def test_retry_on_failed_analysis_returns_202(
    client: TestClient, failed_analysis: FitAnalysis
) -> None:
    response = client.post(f"/analyses/{failed_analysis.job_doc_id}/retry")
    assert response.status_code == 202


def test_retry_on_ready_analysis_returns_409(
    client: TestClient, ready_analysis: FitAnalysis
) -> None:
    # Recomputing a good analysis silently costs money and can change verdicts.
    response = client.post(f"/analyses/{ready_analysis.job_doc_id}/retry")
    assert response.status_code == 409


def test_retry_flips_status_to_pending_before_returning(
    client: TestClient, failed_analysis: FitAnalysis
) -> None:
    client.post(f"/analyses/{failed_analysis.job_doc_id}/retry")

    body = client.get(f"/analyses/{failed_analysis.job_doc_id}").json()
    assert body["status"] == "pending"


def test_unscheduled_job_returns_404(client: TestClient) -> None:
    """No fit_analyses row at all -- e.g. extraction failed, so Task 13's
    scheduler never claimed this pair."""
    assert client.get(f"/analyses/{MISSING_ID}").status_code == 404


def test_retry_on_unscheduled_job_returns_404(client: TestClient) -> None:
    assert client.post(f"/analyses/{MISSING_ID}/retry").status_code == 404


def test_list_analyses_includes_scheduled_jobs(
    client: TestClient, ready_analysis: FitAnalysis
) -> None:
    body = client.get("/analyses").json()
    matching = [item for item in body if item["job_doc_id"] == str(ready_analysis.job_doc_id)]
    assert len(matching) == 1
    assert matching[0]["title"] == "Senior Backend Engineer"
    assert matching[0]["company"] == "Acme"
    assert matching[0]["status"] == "ready"
    assert matching[0]["overall_score"] == 0.75
