"""``fit_analyses``, ``requirement_matches``, ``match_evidence``: the
persisted output of the fit-analysis engine (Task 13, spec §5).

Deliberately no per-requirement score column on ``RequirementMatch``: the
weight is fully derivable from ``verdict`` via ``VERDICT_WEIGHT``
(``analysis/scoring.py``); persisting it would store a computed value that
can drift from its inputs. See spec §4's update note.
"""

import uuid
from typing import Literal

from sqlalchemy import Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey, status_enum

FitAnalysisStatus = Literal["pending", "ready", "failed"]
RequirementVerdictValue = Literal["strong", "partial", "missing"]

# A distinct enum name from document_status/document_extraction_status --
# constraints render as ck_<table>_<enum name>, and both are already taken.
_STATUS = status_enum("fit_analysis_status")

_VERDICT = Enum(
    "strong",
    "partial",
    "missing",
    name="requirement_match_verdict",
    native_enum=False,
    create_constraint=True,
)


class FitAnalysis(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "fit_analyses"

    resume_doc_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_doc_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[FitAnalysisStatus] = mapped_column(
        _STATUS, nullable=False, default="pending", server_default="pending"
    )
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Null until ``status == 'ready'``. Computed in Python, never by the LLM."""

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    matches: Mapped[list["RequirementMatch"]] = relationship(
        back_populates="fit_analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (UniqueConstraint("resume_doc_id", "job_doc_id"),)


class RequirementMatch(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "requirement_matches"

    fit_analysis_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fit_analyses.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[RequirementVerdictValue] = mapped_column(_VERDICT, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    fit_analysis: Mapped["FitAnalysis"] = relationship(back_populates="matches")
    evidence: Mapped[list["MatchEvidence"]] = relationship(
        back_populates="requirement_match",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MatchEvidence(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "match_evidence"

    requirement_match_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("requirement_matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_unit_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("evidence_units.id", ondelete="CASCADE"), nullable=False
    )

    requirement_match: Mapped["RequirementMatch"] = relationship(back_populates="evidence")
