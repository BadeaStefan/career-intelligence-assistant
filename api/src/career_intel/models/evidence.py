"""``evidence_units``: resume-only extracted skills, achievements, and roles.

``char_start``/``char_end`` are nullable -- an unlocatable quote (spec
section 3) still supports a fit verdict, it just can't be highlighted.
"""

import uuid
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from career_intel.constants import EMBEDDING_DIM
from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey

EvidenceKind = Literal["skill", "achievement", "role"]

_KIND = Enum(
    "skill", "achievement", "role", name="evidence_kind", native_enum=False, create_constraint=True
)


class EvidenceUnit(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "evidence_units"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[EvidenceKind] = mapped_column(_KIND, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
