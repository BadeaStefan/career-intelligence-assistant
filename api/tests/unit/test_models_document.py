import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.models import Document


async def test_document_defaults_to_pending(session: AsyncSession) -> None:
    doc = Document(kind="job", source="paste", raw_text="Senior Engineer, Datadog...")

    session.add(doc)
    await session.flush()

    assert doc.id is not None
    assert doc.status == "pending"
    assert doc.extraction_status == "pending"
    assert doc.created_at is not None


async def test_status_and_extraction_status_move_independently(session: AsyncSession) -> None:
    """A document whose extraction failed is still usable.

    ``status`` answers "is this document usable at all"; ``extraction_status``
    answers "did we get structured records out of it". A job with failed
    extraction is still answerable via chunk retrieval, so collapsing these
    into one column would mark a working document broken. Spec section 3.
    """
    doc = Document(
        kind="job",
        source="paste",
        raw_text="...",
        status="ready",
        extraction_status="failed",
    )

    session.add(doc)
    await session.flush()

    stored = (await session.execute(select(Document))).scalar_one()
    assert stored.status == "ready"
    assert stored.extraction_status == "failed"


async def test_database_rejects_an_unknown_kind(session: AsyncSession) -> None:
    """The enum is enforced by the database, not by convention.

    An Enum declared without ``create_constraint=True`` is a bare VARCHAR that
    accepts anything -- a column that reads as constrained while enforcing
    nothing. Written as raw SQL so it tests the constraint rather than
    SQLAlchemy's client-side coercion.
    """
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO documents (id, kind, source, raw_text)"
                " VALUES (gen_random_uuid(), 'banana', 'paste', 'x')"
            )
        )
