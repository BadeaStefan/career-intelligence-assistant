import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.ingest.pipeline import enrich_document
from career_intel.llm.fakes import FakeEmbedder, FakeLLM
from career_intel.models import Chunk, Document, EvidenceUnit, Requirement
from tests.fixtures.builders import RESUME_LINES

RAW = "\n".join(RESUME_LINES)

JOB_RAW = (
    "Senior Backend Engineer at Datadog.\n\n"
    "Requirements: 5+ years Python, Kubernetes at scale, Go preferred."
)

RESUME_EXTRACTION_PAYLOAD = {
    "evidence": [
        {
            "kind": "achievement",
            "text": "Built a large-scale event store",
            # verbatim substring of RAW -- must locate.
            "quote": "Built a sharded event store handling 40k requests per second.",
        },
        {
            "kind": "skill",
            "text": "Cross-team leadership",
            # not present in RAW -- must degrade to a null span, not guess.
            "quote": "coordinated a company-wide reorganisation",
        },
    ]
}

JOB_EXTRACTION_PAYLOAD = {
    "title": "Senior Backend Engineer",
    "company": "Datadog",
    "requirements": [
        {"text": "5+ years Python", "importance": "required", "category": "language"},
        {"text": "Kubernetes at scale", "importance": "required", "category": "platform"},
    ],
}

MALFORMED_PAYLOAD = {"nonsense": True}


async def _seed_document(
    session: AsyncSession,
    *,
    kind: str,
    raw_text: str,
    title: str | None = None,
    company: str | None = None,
) -> Document:
    document = Document(
        kind=kind,
        source="paste",
        raw_text=raw_text,
        status="ready",
        title=title,
        company=company,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


async def test_resume_ingest_produces_located_evidence(session: AsyncSession, fake_embedder):
    fake_llm = FakeLLM(structured_responses=[RESUME_EXTRACTION_PAYLOAD])
    doc = await _seed_document(session, kind="resume", raw_text=RAW)

    await enrich_document(doc.id, llm=fake_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.status == "ready"
    assert doc.extraction_status == "ready"

    units = (await session.execute(select(EvidenceUnit))).scalars().all()
    located = [u for u in units if u.char_start is not None]
    unlocated = [u for u in units if u.char_start is None]
    assert located, "at least one unit should locate"
    assert unlocated, "the deliberately-altered quote should stay null rather than guess"
    for unit in located:
        assert doc.raw_text[unit.char_start : unit.char_end]

    chunks = (await session.execute(select(Chunk))).scalars().all()
    assert chunks


async def test_extraction_failure_degrades_to_chunks(session: AsyncSession, fake_embedder):
    failing_llm = FakeLLM(structured_responses=[MALFORMED_PAYLOAD, MALFORMED_PAYLOAD])
    doc = await _seed_document(session, kind="resume", raw_text=RAW)

    await enrich_document(doc.id, llm=failing_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.status == "ready"  # still usable
    assert doc.extraction_status == "failed"
    assert (await session.execute(select(Chunk))).scalars().all()
    assert (await session.execute(select(EvidenceUnit))).scalars().all() == []


async def test_job_ingest_produces_requirements(session: AsyncSession, fake_embedder):
    fake_llm = FakeLLM(structured_responses=[JOB_EXTRACTION_PAYLOAD])
    doc = await _seed_document(session, kind="job", raw_text=JOB_RAW)

    await enrich_document(doc.id, llm=fake_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.extraction_status == "ready"

    requirements = (await session.execute(select(Requirement))).scalars().all()
    assert {r.text for r in requirements} == {"5+ years Python", "Kubernetes at scale"}
    assert [r.ordinal for r in requirements] == sorted(r.ordinal for r in requirements)


async def test_job_ingest_records_the_extracted_title_and_company(
    session: AsyncSession, fake_embedder
):
    """A job pasted without metadata gets its name from extraction.

    Without this the rail has nothing to render but "Untitled role", which is
    what every job looked like while the extracted title was computed and then
    thrown away.
    """
    fake_llm = FakeLLM(structured_responses=[JOB_EXTRACTION_PAYLOAD])
    doc = await _seed_document(session, kind="job", raw_text=JOB_RAW)

    await enrich_document(doc.id, llm=fake_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.title == "Senior Backend Engineer"
    assert doc.company == "Datadog"


async def test_user_supplied_title_outranks_the_extracted_one(
    session: AsyncSession, fake_embedder
):
    """What the user typed is better information than what the model inferred.

    The two are written by different actors at different times, and extraction
    lands second -- so it must fill blanks rather than overwrite.
    """
    fake_llm = FakeLLM(structured_responses=[JOB_EXTRACTION_PAYLOAD])
    doc = await _seed_document(
        session,
        kind="job",
        raw_text=JOB_RAW,
        title="Backend role I actually want",
        company="Datadog EMEA",
    )

    await enrich_document(doc.id, llm=fake_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.title == "Backend role I actually want"
    assert doc.company == "Datadog EMEA"


async def test_resume_ingest_leaves_title_and_company_alone(
    session: AsyncSession, fake_embedder
):
    """Only the job branch has a title to record; the resume branch must not
    reach for one."""
    fake_llm = FakeLLM(structured_responses=[RESUME_EXTRACTION_PAYLOAD])
    doc = await _seed_document(session, kind="resume", raw_text=RAW)

    await enrich_document(doc.id, llm=fake_llm, embedder=fake_embedder)

    await session.refresh(doc)
    assert doc.title is None
    assert doc.company is None
