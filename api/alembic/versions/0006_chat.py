"""chat_sessions, chat_messages: grounded Q&A over cached fit data (Task 18, spec §6).

Scope lives on chat_messages, not chat_sessions: the session only binds
which job the dock is open on (job_doc_id, nullable for "all jobs"), while
each message independently records the scope it was asked under so history
re-renders faithfully after the toggle is flipped mid-conversation. See
career_intel.models.chat's module docstring.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_doc_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_doc_id"],
            ["documents.id"],
            name=op.f("fk_chat_sessions_job_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "user", "assistant", name="chat_role", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("job", "all", name="chat_scope", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_messages_session_id_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
