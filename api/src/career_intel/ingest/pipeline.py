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
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.db import get_session_factory
from career_intel.models import Document

logger = structlog.get_logger(__name__)


async def enrich_document(document_id: uuid.UUID) -> None:
    """Build structured records for a document.

    Wrapped so that *any* failure settles ``extraction_status`` before the
    exception propagates. This closes one of the two ways a row can be
    stranded at ``pending``: an exception thrown while the process stays
    alive. The other -- the process dying outright -- is closed by
    :func:`fail_orphaned_pending_rows` at startup.

    The exception is re-raised rather than swallowed so it still reaches the
    logs; the row is merely settled first.
    """
    async with get_session_factory()() as session:
        try:
            await _run_enrichment(session, document_id)
        except Exception:
            logger.exception("enrichment_failed", document_id=str(document_id))
            await _settle(session, document_id, "failed")
            raise


async def _run_enrichment(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Produce chunks, evidence units, and requirements.

    Phase 2 fills this in. The seam exists now so the failure handling around
    it is written and tested against a real call site rather than retrofitted
    onto working code.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise LookupError(f"document {document_id} disappeared before enrichment")

    await _settle(session, document_id, "ready")


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
