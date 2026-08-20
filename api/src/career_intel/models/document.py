"""The ``documents`` table: one row per resume or job posting."""

from typing import Literal

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey, status_enum

DocumentKind = Literal["resume", "job"]
DocumentSource = Literal["upload", "paste"]
ProcessingStatus = Literal["pending", "ready", "failed"]

# native_enum=False renders these as VARCHAR rather than a Postgres ENUM type.
# Postgres enums need an ALTER TYPE to add a value and cannot drop one at all,
# which makes them expensive to change; a CHECK constraint is a plain migration.
#
# create_constraint=True is required and easy to miss: SQLAlchemy has defaulted
# it to False since 1.4, so declaring an Enum without it produces a bare VARCHAR
# that accepts any string -- a column that reads as constrained while enforcing
# nothing.
_KIND = Enum("resume", "job", name="document_kind", native_enum=False, create_constraint=True)
_SOURCE = Enum(
    "upload", "paste", name="document_source", native_enum=False, create_constraint=True
)

# Distinct names: both columns are pending/ready/failed, but constraints are
# named ck_<table>_<enum name>, so reusing one name would collide.
_STATUS = status_enum("document_status")
_EXTRACTION_STATUS = status_enum("document_extraction_status")


class Document(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "documents"

    kind: Mapped[DocumentKind] = mapped_column(_KIND, nullable=False)
    source: Mapped[DocumentSource] = mapped_column(_SOURCE, nullable=False)

    title: Mapped[str | None] = mapped_column(String(512))
    company: Mapped[str | None] = mapped_column(String(512))
    filename: Mapped[str | None] = mapped_column(String(512))

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ProcessingStatus] = mapped_column(
        _STATUS, nullable=False, default="pending", server_default="pending"
    )
    """Is this document usable at all?

    ``pending`` while ingest runs, ``ready`` once its text is stored,
    ``failed`` if parsing broke or the process died mid-ingest.
    """

    extraction_status: Mapped[ProcessingStatus] = mapped_column(
        _EXTRACTION_STATUS, nullable=False, default="pending", server_default="pending"
    )
    """Did structured extraction produce records for this document?

    Deliberately separate from ``status``. Extraction failing does not make a
    document unusable -- it still has chunks, so it is still answerable in
    chat; it just cannot take part in a fit analysis. Collapsing the two would
    mark a working document broken. Spec section 3.
    """
