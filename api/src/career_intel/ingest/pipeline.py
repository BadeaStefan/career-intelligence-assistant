"""Background enrichment and the startup sweep that keeps it honest.

Parsing deliberately happens in the request handler, not here: it is fast,
local, and can fail for reasons the user can act on, so it belongs in a
response rather than in a row they have to discover by polling. This module
owns the slow, networked half -- chunking, extraction, embedding -- which
genuinely cannot block an upload.
"""

import uuid

import structlog
from sqlalchemy import case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_intel.config import get_settings
from career_intel.db import get_session_factory
from career_intel.ingest.chunking import chunk_text
from career_intel.ingest.extraction import extract_job, extract_resume
from career_intel.ingest.locate import locate_quote
from career_intel.ingest.schemas import ExtractedEvidence, ExtractedRequirement
from career_intel.llm.openai_client import OpenAIClient
from career_intel.llm.protocol import Embedder, LLMClient
from career_intel.models import Chunk, Document, EvidenceUnit, Requirement

logger = structlog.get_logger(__name__)


async def enrich_document(
    document_id: uuid.UUID,
    *,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
) -> None:
    """Build structured records for a document.

    Wrapped so that *any* failure settles ``extraction_status`` before the
    exception propagates. This closes one of the two ways a row can be
    stranded at ``pending``: an exception thrown while the process stays
    alive. The other -- the process dying outright -- is closed by
    :func:`fail_orphaned_pending_rows` at startup.

    The exception is re-raised rather than swallowed so it still reaches the
    logs; the row is merely settled first.

    ``llm``/``embedder`` default to ``None``, meaning "build the real
    clients from settings" -- tests inject fakes. A single ``OpenAIClient``
    satisfies both Protocols, so the common case builds one client, not two.
    """
    session_factory = get_session_factory()

    if llm is None or embedder is None:
        client = OpenAIClient(session_factory=session_factory, settings=get_settings())
        llm = llm or client
        embedder = embedder or client

    try:
        await _run_enrichment(session_factory, document_id, llm=llm, embedder=embedder)
    except Exception:
        logger.exception("enrichment_failed", document_id=str(document_id))
        async with session_factory() as session:
            await _settle(session, document_id, "failed")
        raise


async def _run_enrichment(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: uuid.UUID,
    *,
    llm: LLMClient,
    embedder: Embedder,
) -> None:
    """Produce chunks, evidence units, and requirements.

    All network work (extraction, embedding) completes *before* any
    transaction opens; the read that fetches ``raw_text`` and the write that
    persists the results are two separate sessions, so no transaction is
    ever held open across an OpenAI call (non-negotiable #4).
    """
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise LookupError(f"document {document_id} disappeared before enrichment")
        raw_text = document.raw_text
        kind = document.kind

    chunks = chunk_text(raw_text)

    evidence_items: list[ExtractedEvidence] = []
    requirement_items: list[ExtractedRequirement] = []
    extraction_status = "failed"

    if kind == "resume":
        resume_extraction = await extract_resume(llm, raw_text)
        if resume_extraction is not None:
            extraction_status = "ready"
            evidence_items = resume_extraction.evidence
    else:
        job_extraction = await extract_job(llm, raw_text)
        if job_extraction is not None:
            extraction_status = "ready"
            requirement_items = job_extraction.requirements

    texts = (
        [chunk.text for chunk in chunks]
        + [item.text for item in evidence_items]
        + [item.text for item in requirement_items]
    )
    embeddings = await embedder.embed(texts)
    chunk_embeddings = embeddings[: len(chunks)]
    evidence_embeddings = embeddings[len(chunks) : len(chunks) + len(evidence_items)]
    requirement_embeddings = embeddings[len(chunks) + len(evidence_items) :]

    chunk_rows = [
        Chunk(
            document_id=document_id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            embedding=embedding,
        )
        for chunk, embedding in zip(chunks, chunk_embeddings, strict=True)
    ]

    evidence_rows = []
    for item, embedding in zip(evidence_items, evidence_embeddings, strict=True):
        span = locate_quote(raw_text, item.quote)
        evidence_rows.append(
            EvidenceUnit(
                document_id=document_id,
                kind=item.kind,
                text=item.text,
                char_start=span.start if span else None,
                char_end=span.end if span else None,
                embedding=embedding,
            )
        )

    requirement_rows = [
        Requirement(
            document_id=document_id,
            ordinal=ordinal,
            text=item.text,
            importance=item.importance,
            category=item.category,
            embedding=embedding,
        )
        for ordinal, (item, embedding) in enumerate(
            zip(requirement_items, requirement_embeddings, strict=True)
        )
    ]

    async with session_factory() as session:
        session.add_all([*chunk_rows, *evidence_rows, *requirement_rows])
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(extraction_status=extraction_status)
        )
        await session.commit()


async def _settle(session: AsyncSession, document_id: uuid.UUID, status: str) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(extraction_status=status)
    )
    await session.commit()


async def fail_orphaned_pending_rows(session: AsyncSession) -> int:
    """Settle rows whose background task died with a previous process.

    Enrichment runs in-process, so it cannot outlive the process. Any row
    still ``pending`` when the process boots is therefore provably orphaned:
    nothing is left that could ever finish it.

    Deliberately no age threshold. A row younger than the cutoff would survive
    the sweep and hang forever, which is precisely the failure this exists to
    prevent -- the age check is a leftover from periodic-sweep designs, where
    live tasks must not be interrupted. Spec section 3.
    """
    # One statement, so the return count is rows settled rather than column
    # updates -- a row with both columns pending is one orphan, not two.
    result = await session.execute(
        update(Document)
        .where(
            or_(
                Document.status == "pending",
                Document.extraction_status == "pending",
            )
        )
        .values(
            status=case(
                (Document.status == "pending", "failed"),
                else_=Document.status,
            ),
            extraction_status=case(
                (Document.extraction_status == "pending", "failed"),
                else_=Document.extraction_status,
            ),
        )
        .returning(Document.id)
    )
    settled = len(result.fetchall())

    await session.commit()

    if settled:
        logger.warning("swept_orphaned_pending_rows", count=settled)

    return settled


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())
