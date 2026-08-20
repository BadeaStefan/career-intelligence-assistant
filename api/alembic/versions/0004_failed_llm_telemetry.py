"""Record failed LLM calls without inventing token usage or cost.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("status", sa.String(length=16), server_default="succeeded", nullable=False),
    )
    op.add_column("llm_calls", sa.Column("error_type", sa.String(length=128), nullable=True))
    op.create_check_constraint(
        "ck_llm_calls_status", "llm_calls", "status IN ('succeeded', 'failed')"
    )
    op.alter_column("llm_calls", "prompt_tokens", existing_type=sa.Integer(), nullable=True)
    op.alter_column("llm_calls", "completion_tokens", existing_type=sa.Integer(), nullable=True)
    op.alter_column("llm_calls", "cost_usd", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute(
        "UPDATE llm_calls SET prompt_tokens = 0, completion_tokens = 0, cost_usd = 0 "
        "WHERE prompt_tokens IS NULL OR completion_tokens IS NULL OR cost_usd IS NULL"
    )
    op.alter_column("llm_calls", "cost_usd", existing_type=sa.Float(), nullable=False)
    op.alter_column("llm_calls", "completion_tokens", existing_type=sa.Integer(), nullable=False)
    op.alter_column("llm_calls", "prompt_tokens", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("ck_llm_calls_status", "llm_calls", type_="check")
    op.drop_column("llm_calls", "error_type")
    op.drop_column("llm_calls", "status")
