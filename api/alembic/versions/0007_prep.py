"""interview_preps, prep_questions: interview questions derived from a
completed fit analysis (Task 20, spec §7).

No new retrieval: prep_questions.evidence_ids points into evidence_units the
fit analysis already linked via match_evidence -- see career_intel.prep.
service's module docstring. ordinal exists for the same reason
chat_messages.ordinal does (career_intel.models.chat's docstring): every
question for one prep is written in a single transaction, so created_at
cannot order them.

Named 0007, not 0006 -- 0006 is already taken by Task 18's chat migration.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_preps",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("fit_analysis_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fit_analysis_id"],
            ["fit_analyses.id"],
            name=op.f("fk_interview_preps_fit_analysis_id_fit_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_preps")),
        sa.UniqueConstraint("fit_analysis_id", name=op.f("uq_interview_preps_fit_analysis_id")),
    )

    op.create_table(
        "prep_questions",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_prep_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("why_they_will_ask", sa.Text(), nullable=False),
        sa.Column("how_to_frame", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.ARRAY(sa.UUID(as_uuid=True)), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_prep_id"],
            ["interview_preps.id"],
            name=op.f("fk_prep_questions_interview_prep_id_interview_preps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_prep_questions_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_questions")),
    )


def downgrade() -> None:
    op.drop_table("prep_questions")
    op.drop_table("interview_preps")
