"""Initial schema: pgvector extension and the documents table.

Revision ID: 0001
Revises:
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Must precede any table declaring a vector column. Later migrations add
    # those; creating the extension here keeps it a one-time concern.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "resume",
                "job",
                name="document_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "upload",
                "paste",
                name="document_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("company", sa.String(length=512), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        # Two pending/ready/failed columns with deliberately distinct enum
        # names: constraints render as ck_<table>_<enum name>, so a shared name
        # would produce two constraints competing for one identifier.
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "ready",
                "failed",
                name="document_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "extraction_status",
            sa.Enum(
                "pending",
                "ready",
                "failed",
                name="document_extraction_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )

    # The dashboard lists documents newest-first and filters by kind.
    op.create_index("ix_documents_kind_created_at", "documents", ["kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_kind_created_at", table_name="documents")
    op.drop_table("documents")
    # The extension is deliberately left in place: other databases on the same
    # instance may rely on it, and dropping it would cascade into their tables.
