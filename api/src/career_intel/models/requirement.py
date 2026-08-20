"""``requirements``: job-only extracted requirements.

Linked to its job by foreign key, written by Python after a per-document
extraction call -- the model is never asked which job a requirement belongs
to, so it cannot get it wrong (spec section 4).
"""

import uuid
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from career_intel.constants import EMBEDDING_DIM
from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey

RequirementImportance = Literal["required", "preferred"]

_IMPORTANCE = Enum(
    "required",
    "preferred",
    name="requirement_importance",
    native_enum=False,
    create_constraint=True,
)


class Requirement(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "requirements"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[RequirementImportance] = mapped_column(_IMPORTANCE, nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
