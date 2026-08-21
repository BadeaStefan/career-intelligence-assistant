"""``interview_preps`` and ``prep_questions``: interview questions derived
from a completed fit analysis (Task 20, spec §7).

No new retrieval happens to build these: every requirement, verdict, and
evidence unit a question can cite already exists in the fit analysis it was
generated from (``analysis/engine.py``'s persisted output) -- see
``prep/service.py``'s module docstring.

``ordinal`` exists on ``PrepQuestion`` for the same reason it exists on
``ChatMessage`` (``models/chat.py``'s docstring): every question for one
prep is written in a single transaction, so Postgres' ``now()`` -- constant
for the whole transaction -- ties every row's ``created_at``, leaving
relative order a coin flip without an explicit ordinal.

``evidence_ids`` is a plain Postgres array of UUIDs, not a join table like
``match_evidence``: a prep question's citations are only ever read back with
that one question (never queried relationally the way the dashboard joins
verdicts to evidence spans), the same asymmetry ``models/chat.py`` already
draws for ``ChatMessage.citations`` -- except here every element already
*is* an evidence unit id, with no extra shape to carry, so a typed array is
enough; a chat citation additionally carries the resolved span, which is why
that column is ``jsonb`` instead.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey


class InterviewPrep(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "interview_preps"

    fit_analysis_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("fit_analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    """UNIQUE: exactly one prep per fit analysis -- this is also the
    constraint the POST route's ``ON CONFLICT (fit_analysis_id) DO NOTHING``
    upsert relies on to make concurrent generation race-safe."""

    model: Mapped[str] = mapped_column(String(128), nullable=False)

    questions: Mapped[list["PrepQuestion"]] = relationship(
        back_populates="interview_prep",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PrepQuestion.ordinal",
    )


class PrepQuestion(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "prep_questions"

    interview_prep_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("interview_preps.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    why_they_will_ask: Mapped[str] = mapped_column(Text, nullable=False)
    how_to_frame: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PgUUID(as_uuid=True)), nullable=False, default=list
    )
    """Validated before persisting (``analysis.validation.validate_handles``,
    non-negotiable #7) -- only evidence units actually offered for this
    question's own requirement, never a bare handle."""

    interview_prep: Mapped["InterviewPrep"] = relationship(back_populates="questions")
