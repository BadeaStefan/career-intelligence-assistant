"""fit_analyses, requirement_matches, match_evidence: the fit-analysis engine.

No score column on requirement_matches -- the weight is fully derivable from
verdict via VERDICT_WEIGHT (analysis/scoring.py); persisting it would store a
computed value that can drift from its inputs. See spec §4's update note.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fit_analyses",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_doc_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_doc_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "ready",
                "failed",
                name="fit_analysis_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["resume_doc_id"],
            ["documents.id"],
            name=op.f("fk_fit_analyses_resume_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_doc_id"],
            ["documents.id"],
            name=op.f("fk_fit_analyses_job_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fit_analyses")),
        sa.UniqueConstraint(
            "resume_doc_id",
            "job_doc_id",
            name=op.f("uq_fit_analyses_resume_doc_id"),
        ),
    )

    op.create_table(
        "requirement_matches",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("fit_analysis_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "verdict",
            sa.Enum(
                "strong",
                "partial",
                "missing",
                name="requirement_match_verdict",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fit_analysis_id"],
            ["fit_analyses.id"],
            name=op.f("fk_requirement_matches_fit_analysis_id_fit_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_matches_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_matches")),
    )

    op.create_table(
        "match_evidence",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_match_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_unit_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requirement_match_id"],
            ["requirement_matches.id"],
            name=op.f("fk_match_evidence_requirement_match_id_requirement_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"],
            ["evidence_units.id"],
            name=op.f("fk_match_evidence_evidence_unit_id_evidence_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_evidence")),
    )


def downgrade() -> None:
    op.drop_table("match_evidence")
    op.drop_table("requirement_matches")
    op.drop_table("fit_analyses")
