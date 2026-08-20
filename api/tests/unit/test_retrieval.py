"""Nearest-evidence and nearest-chunk retrieval, plus their traces.

Embeddings are hand-built one-hot vectors rather than ``FakeEmbedder``
output: a hash-based vector gives no control over which one is nearest a
given query, and these tests exist specifically to prove ranking and
per-document scoping.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.analysis.retrieval import (
    ChunkCandidate,
    EvidenceCandidate,
    nearest_chunks,
    nearest_evidence,
)
from career_intel.constants import EMBEDDING_DIM
from career_intel.models import Chunk, Document, EvidenceUnit
from career_intel.models.telemetry import RetrievalTrace


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 1.0
    return vector


def _near(index: int) -> list[float]:
    """A vector close to, but not exactly, the one-hot vector at ``index``."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 0.9
    vector[(index + 1) % EMBEDDING_DIM] = 0.1
    return vector


async def _seed_document(session: AsyncSession, *, kind: str = "resume") -> Document:
    document = Document(kind=kind, source="paste", raw_text="x", status="ready")
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def _seed_evidence(
    session: AsyncSession, *, document_id: UUID, text: str, embedding: list[float]
) -> EvidenceUnit:
    unit = EvidenceUnit(
        document_id=document_id,
        kind="skill",
        text=text,
        char_start=None,
        char_end=None,
        embedding=embedding,
    )
    session.add(unit)
    await session.commit()
    await session.refresh(unit)
    return unit


async def _seed_chunk(
    session: AsyncSession,
    *,
    document_id: UUID,
    ordinal: int,
    text: str,
    embedding: list[float],
) -> Chunk:
    chunk = Chunk(
        document_id=document_id,
        ordinal=ordinal,
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=embedding,
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)
    return chunk


async def test_nearest_evidence_ranks_closest_first_and_scopes_to_document(
    session: AsyncSession,
):
    resume = await _seed_document(session, kind="resume")
    other = await _seed_document(session, kind="resume")

    unit1 = await _seed_evidence(
        session, document_id=resume.id, text="one", embedding=_one_hot(0)
    )
    unit2 = await _seed_evidence(
        session, document_id=resume.id, text="two", embedding=_one_hot(1)
    )
    unit3 = await _seed_evidence(
        session, document_id=resume.id, text="three", embedding=_one_hot(2)
    )
    # Belongs to a different document, but is the closest vector overall --
    # must never appear in results scoped to `resume`.
    foreign = await _seed_evidence(
        session, document_id=other.id, text="foreign", embedding=_near(1)
    )

    results = await nearest_evidence(
        session, resume_doc_id=resume.id, requirement_embedding=_near(1), k=5
    )

    assert [c.evidence_unit_id for c in results][0] == unit2.id
    result_ids = {c.evidence_unit_id for c in results}
    assert foreign.id not in result_ids
    assert result_ids == {unit1.id, unit2.id, unit3.id}

    assert results[0].handle == "e1"
    assert results[1].handle == "e2"
    assert all(isinstance(c, EvidenceCandidate) for c in results)


async def test_nearest_evidence_writes_a_retrieval_trace(session: AsyncSession):
    resume = await _seed_document(session, kind="resume")
    unit1 = await _seed_evidence(
        session, document_id=resume.id, text="one", embedding=_one_hot(0)
    )
    await _seed_evidence(session, document_id=resume.id, text="two", embedding=_one_hot(1))

    results = await nearest_evidence(
        session, resume_doc_id=resume.id, requirement_embedding=_one_hot(0), k=5
    )

    from career_intel.db import get_session_factory

    async with get_session_factory()() as fresh:
        traces = (await fresh.execute(select(RetrievalTrace))).scalars().all()

    assert len(traces) == 1
    trace = traces[0]
    assert str(resume.id) in trace.query
    result_ids = {c["id"] for c in trace.results["candidates"]}
    assert result_ids == {str(c.evidence_unit_id) for c in results}
    assert result_ids == {str(unit1.id), str(results[1].evidence_unit_id)}
    for candidate in trace.results["candidates"]:
        assert "score" in candidate
        assert "handle" in candidate


async def test_nearest_chunks_ranks_closest_first_and_scopes_to_document(
    session: AsyncSession,
):
    doc = await _seed_document(session, kind="resume")
    other = await _seed_document(session, kind="resume")

    chunk1 = await _seed_chunk(
        session, document_id=doc.id, ordinal=0, text="one", embedding=_one_hot(0)
    )
    chunk2 = await _seed_chunk(
        session, document_id=doc.id, ordinal=1, text="two", embedding=_one_hot(1)
    )
    chunk3 = await _seed_chunk(
        session, document_id=doc.id, ordinal=2, text="three", embedding=_one_hot(2)
    )
    foreign = await _seed_chunk(
        session, document_id=other.id, ordinal=0, text="foreign", embedding=_near(1)
    )

    results = await nearest_chunks(
        session, document_id=doc.id, query_embedding=_near(1), k=5
    )

    assert [c.chunk_id for c in results][0] == chunk2.id
    result_ids = {c.chunk_id for c in results}
    assert foreign.id not in result_ids
    assert result_ids == {chunk1.id, chunk2.id, chunk3.id}

    assert results[0].handle == "c1"
    assert results[1].handle == "c2"
    assert all(isinstance(c, ChunkCandidate) for c in results)
    for candidate in results:
        assert candidate.char_start is not None
        assert candidate.char_end is not None


async def test_nearest_chunks_writes_a_retrieval_trace(session: AsyncSession):
    doc = await _seed_document(session, kind="resume")
    chunk1 = await _seed_chunk(
        session, document_id=doc.id, ordinal=0, text="one", embedding=_one_hot(0)
    )
    await _seed_chunk(session, document_id=doc.id, ordinal=1, text="two", embedding=_one_hot(1))

    results = await nearest_chunks(
        session, document_id=doc.id, query_embedding=_one_hot(0), k=5
    )

    from career_intel.db import get_session_factory

    async with get_session_factory()() as fresh:
        traces = (await fresh.execute(select(RetrievalTrace))).scalars().all()

    assert len(traces) == 1
    trace = traces[0]
    assert str(doc.id) in trace.query
    result_ids = {c["id"] for c in trace.results["candidates"]}
    assert result_ids == {str(c.chunk_id) for c in results}
    assert result_ids == {str(chunk1.id), str(results[1].chunk_id)}
    for candidate in trace.results["candidates"]:
        assert "score" in candidate
        assert "handle" in candidate
