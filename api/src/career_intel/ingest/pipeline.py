"""Background enrichment and the startup sweep that keeps it honest.

Parsing deliberately happens in the request handler, not here: it is fast,
local, and can fail for reasons the user can act on, so it belongs in a
response rather than in a row they have to discover by polling. This module
owns the slow, networked half -- chunking, extraction, embedding -- which
genuinely cannot block an upload.
"""

import uuid

import structlog
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_intel.analysis.engine import run_fit_analysis, schedule_fit_analyses
from career_intel.config import get_settings
from career_intel.db import get_session_factory
from career_intel.ingest.chunking import chunk_text
from career_intel.ingest.extraction import extract_job, extract_resume
from career_intel.ingest.locate import locate_quote
from career_intel.ingest.schemas import ExtractedEvidence, ExtractedRequirement
from career_intel.llm.openai_client import OpenAIClient
from career_intel.llm.protocol import Embedder, LLMClient
from career_intel.models import ChatSession, Chunk, Document, EvidenceUnit, Requirement
from career_intel.models.analysis import FitAnalysis

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
    extracted_title: str | None = None
    extracted_company: str | None = None

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
            extracted_title = job_extraction.title
            extracted_company = job_extraction.company

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
            .values(
                extraction_status=extraction_status,
                # coalesce, not assignment: the row may already carry a title
                # the user typed when adding the posting, and that is better
                # information than the model's reading of the same text. This
                # write lands second, so it must fill blanks rather than
                # replace. Both are NULL for a resume, where the job branch
                # never ran and there is nothing to record.
                title=func.coalesce(Document.title, extracted_title),
                company=func.coalesce(Document.company, extracted_company),
            )
        )
        await session.commit()

    # Fires regardless of whether this document was the resume or the job,
    # and regardless of whether its own extraction just succeeded or
    # degraded to chunk-only: schedule_fit_analyses's own WHERE clause only
    # ever claims pairs where both sides are actually 'ready', so calling it
    # unconditionally is correct and a no-op when nothing qualifies. A
    # failure here must not fail *this* document -- its own extraction_status
    # is already settled above -- so it is caught and logged, never
    # propagated.
    try:
        await _trigger_fit_analyses(session_factory, llm=llm)
    except Exception:
        logger.exception("fit_analysis_trigger_failed", document_id=str(document_id))


async def _trigger_fit_analyses(
    session_factory: async_sessionmaker[AsyncSession], *, llm: LLMClient
) -> None:
    """Reuses the same ``llm`` this document's own enrichment used.

    Deliberately does *not* build its own ``OpenAIClient``: ``enrich_document``
    accepts ``llm`` precisely so tests can inject a fake, and a fresh real
    client built here would silently reach api.openai.com the moment a test
    seeds both a ready resume and a ready job -- exactly the "no network in
    unit tests" rule this project treats as non-negotiable.
    """
    async with session_factory() as session:
        claimed_ids = await schedule_fit_analyses(session)
        if not claimed_ids:
            return
        pairs = (
            await session.execute(
                select(
                    FitAnalysis.resume_doc_id, FitAnalysis.job_doc_id
                ).where(FitAnalysis.id.in_(claimed_ids))
            )
        ).all()

    for resume_doc_id, job_doc_id in pairs:
        try:
            async with session_factory() as session:
                await run_fit_analysis(
                    session, resume_doc_id=resume_doc_id, job_doc_id=job_doc_id, llm=llm
                )
        except Exception:
            # run_fit_analysis has already settled its own row at
            # status='failed' -- including when the failure happened during
            # its own persist step, not just during the LLM calls before it
            # (see engine.py's module docstring) -- and, separately, already
            # logged if even that settle attempt itself failed. This handler
            # only stops one bad pair from blocking the rest of the
            # newly-claimed batch.
            logger.exception(
                "fit_analysis_failed",
                resume_doc_id=str(resume_doc_id),
                job_doc_id=str(job_doc_id),
            )


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

    # fit_analyses has the same orphaning problem: its background task also
    # runs in-process and cannot outlive it. Spec section 3 names both
    # documents and fit_analyses.
    analysis_result = await session.execute(
        update(FitAnalysis)
        .where(FitAnalysis.status == "pending")
        .values(status="failed")
        .returning(FitAnalysis.id)
    )
    settled += len(analysis_result.fetchall())

    await session.commit()

    if settled:
        logger.warning("swept_orphaned_pending_rows", count=settled)

    return settled


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


async def delete_document_and_dependents(session: AsyncSession, document: Document) -> None:
    """Delete one document plus workspace data not linked by its own FK.

    Jobs own their chat sessions directly, so the database cascades those.
    Chat sessions do not point at the resume even though every answer can be
    grounded in it; removing the single workspace resume therefore makes all
    existing sessions stale and requires an explicit workspace-wide cleanup.
    Does not commit.
    """
    if document.kind == "resume":
        await session.execute(delete(ChatSession))

    await session.delete(document)


async def delete_existing_resumes(session: AsyncSession) -> int:
    """Drop every resume-kind document. Does not commit.

    Spec §5: "Uploading a new resume replaces the old one: the old
    ``documents`` row is deleted, analyses cascade away with it, and every
    pair is recomputed against the new resume." Called as part of persisting
    a new resume, so the delete and the insert land in one transaction.

    This is what makes "the current resume" a well-defined phrase. Four call
    sites resolve it four different ways -- newest by ``created_at``, an
    unordered ``.first()``, the first entry of a list response -- and they
    agree only while at most one resume exists. That agreement is an
    invariant, and non-negotiable #11 says an invariant belongs at the write
    path, not in each reader's ORDER BY.

    Plural on purpose: the invariant is what this establishes, not what it
    assumes, so it clears any pre-existing anomaly rather than trusting there
    to be exactly one row.

    Dependent rows (``chunks``, ``evidence_units``, ``fit_analyses`` and
    everything cascading off those) go with it via the FK ``ON DELETE
    CASCADE`` already declared on each. Issued as one bulk DELETE rather than
    a load-then-``session.delete()`` loop: the database does the cascading
    either way, and loading a resume row means loading its ``raw_text``,
    which there is no reason to pull into memory to throw away.
    """
    result = await session.execute(
        delete(Document).where(Document.kind == "resume").returning(Document.id)
    )
    deleted = len(result.fetchall())
    if deleted:
        # A replacement changes the grounding corpus just as surely as an
        # explicit resume deletion, so old chat sessions cannot be reused.
        await session.execute(delete(ChatSession))
    return deleted
