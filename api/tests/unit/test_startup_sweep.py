from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.ingest.pipeline import fail_orphaned_pending_rows
from career_intel.models import Document


async def test_startup_marks_every_pending_row_failed(session: AsyncSession) -> None:
    """A pending row at boot is provably orphaned, regardless of age.

    Ingest runs as an in-process background task, so it cannot outlive the
    process. Any row still pending when the process starts had its task die
    with the previous process.

    Deliberately no age threshold: a row younger than the threshold would
    survive the sweep and then hang forever, because nothing is left to finish
    it -- exactly the failure the sweep exists to prevent. Spec section 3.
    """
    just_created = Document(kind="job", source="paste", raw_text="x", status="pending")
    session.add(just_created)
    await session.flush()

    swept = await fail_orphaned_pending_rows(session)

    await session.refresh(just_created)
    assert swept == 1
    assert just_created.status == "failed"


async def test_sweep_leaves_settled_rows_alone(session: AsyncSession) -> None:
    # Both columns must be settled explicitly: extraction_status defaults to
    # pending, and a row whose enrichment never completed is a genuine orphan
    # that the sweep is right to fail.
    ready = Document(
        kind="job", source="paste", raw_text="x", status="ready", extraction_status="ready"
    )
    failed = Document(
        kind="job", source="paste", raw_text="x", status="failed", extraction_status="failed"
    )
    session.add_all([ready, failed])
    await session.flush()

    swept = await fail_orphaned_pending_rows(session)

    await session.refresh(ready)
    await session.refresh(failed)
    assert swept == 0
    assert ready.status == "ready"
    assert failed.status == "failed"


async def test_sweep_is_idempotent(session: AsyncSession) -> None:
    """Running twice must not re-report work. Startup can retry."""
    session.add(Document(kind="job", source="paste", raw_text="x", status="pending"))
    await session.flush()

    assert await fail_orphaned_pending_rows(session) == 1
    assert await fail_orphaned_pending_rows(session) == 0


async def test_sweep_also_settles_pending_extraction(session: AsyncSession) -> None:
    """extraction_status has the same orphaning problem as status.

    A document whose extraction task died would otherwise sit at pending
    forever while the UI waits for structured records that will never arrive.
    """
    doc = Document(
        kind="job",
        source="paste",
        raw_text="x",
        status="ready",
        extraction_status="pending",
    )
    session.add(doc)
    await session.flush()

    await fail_orphaned_pending_rows(session)

    stored = (await session.execute(select(Document))).scalar_one()
    assert stored.status == "ready"
    assert stored.extraction_status == "failed"
