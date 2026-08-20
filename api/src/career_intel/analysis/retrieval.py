"""Nearest-neighbour retrieval over resume evidence and chunks.

``nearest_evidence`` serves the fit engine (Task 13): given a requirement's
embedding, it finds the resume evidence units closest to it, scoped to one
resume document. ``nearest_chunks`` serves chat (Task 17): given a question's
embedding, it finds the closest raw-text chunks of a document, the lossless
fallback retrieval path.

Score convention: pgvector's ``cosine_distance`` is 0 for identical direction
and grows as vectors diverge, so *smaller* distance means *more* similar. We
report ``score = 1 - distance`` (cosine similarity) on each candidate, so
callers can read "higher score is a better match" -- rows are still selected
by ordering the distance ascending, i.e. the first row has the highest score.

Every call writes its own ``retrieval_traces`` row (ids + scores) in a
short-lived session, separate from the caller's ``session``, for the same
reason ``llm/openai_client.py`` writes ``llm_calls`` rows in their own
session: the caller's session may roll back or still be mid-transaction for
reasons unrelated to whether the trace should exist.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.db import get_session_factory
from career_intel.models import Chunk, EvidenceUnit
from career_intel.models.telemetry import RetrievalTrace
from career_intel.observability import request_id_var


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_unit_id: UUID
    handle: str  # "e1", "e2" -- short handles survive tokenisation; UUIDs do not
    text: str
    score: float


@dataclass(frozen=True)
class ChunkCandidate:
    chunk_id: UUID
    handle: str  # "c1", "c2"
    text: str
    char_start: int
    char_end: int
    score: float


async def nearest_evidence(
    session: AsyncSession,
    *,
    resume_doc_id: UUID,
    requirement_embedding: list[float],
    k: int = 5,
) -> list[EvidenceCandidate]:
    distance = EvidenceUnit.embedding.cosine_distance(requirement_embedding)
    rows = (
        await session.execute(
            select(EvidenceUnit, distance.label("distance"))
            .where(EvidenceUnit.document_id == resume_doc_id)
            .order_by(distance)
            .limit(k)
        )
    ).all()

    candidates = [
        EvidenceCandidate(
            evidence_unit_id=unit.id,
            handle=f"e{index}",
            text=unit.text,
            score=1.0 - unit_distance,
        )
        for index, (unit, unit_distance) in enumerate(rows, start=1)
    ]

    await _write_trace(
        query=f"nearest_evidence resume_doc_id={resume_doc_id}",
        candidates=[
            {"id": str(c.evidence_unit_id), "handle": c.handle, "score": c.score}
            for c in candidates
        ],
    )
    return candidates


async def nearest_chunks(
    session: AsyncSession,
    *,
    document_id: UUID,
    query_embedding: list[float],
    k: int = 5,
) -> list[ChunkCandidate]:
    distance = Chunk.embedding.cosine_distance(query_embedding)
    rows = (
        await session.execute(
            select(Chunk, distance.label("distance"))
            .where(Chunk.document_id == document_id)
            .order_by(distance)
            .limit(k)
        )
    ).all()

    candidates = [
        ChunkCandidate(
            chunk_id=chunk.id,
            handle=f"c{index}",
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            score=1.0 - chunk_distance,
        )
        for index, (chunk, chunk_distance) in enumerate(rows, start=1)
    ]

    await _write_trace(
        query=f"nearest_chunks document_id={document_id}",
        candidates=[
            {"id": str(c.chunk_id), "handle": c.handle, "score": c.score} for c in candidates
        ],
    )
    return candidates


async def _write_trace(*, query: str, candidates: list[dict[str, Any]]) -> None:
    row = RetrievalTrace(
        request_id=request_id_var.get(),
        query=query,
        results={"candidates": candidates},
    )
    async with get_session_factory()() as trace_session:
        trace_session.add(row)
        await trace_session.commit()
