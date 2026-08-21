"""``chat_sessions`` and ``chat_messages`` (Task 18, spec §6).

Scope lives on the *message*, not the session (see ``chat/service.py``'s
module docstring for why): the session only binds which job the dock is
open on, so a session's ``job_doc_id`` is nullable to support the "all jobs"
scope, and each message independently records the scope it was asked under
so the UI can faithfully re-render history after the toggle has been
flipped mid-conversation.

Citations live in a ``jsonb`` column here rather than a join table like
``match_evidence`` -- a deliberate asymmetry (spec §4): fit citations are
queried relationally (the dashboard joins verdicts to evidence spans), but a
chat message's citations are only ever read back with that one message.
"""

import uuid
from typing import Literal

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey

ChatRole = Literal["user", "assistant"]
ChatScope = Literal["job", "all"]

_ROLE = Enum("user", "assistant", name="chat_role", native_enum=False, create_constraint=True)
_SCOPE = Enum("job", "all", name="chat_scope", native_enum=False, create_constraint=True)


class ChatSession(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "chat_sessions"

    job_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    """Which job's dock this session belongs to. Null for a session opened
    without a job in context (e.g. straight into "all jobs" scope)."""

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(_ROLE, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[ChatScope] = mapped_column(_SCOPE, nullable=False)
    """The scope this specific message was asked/answered under -- UI state,
    never inferred, and never shared with the session (see module docstring)."""

    citations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    """Validated handles only (``analysis/validation.validate_handles``).
    Empty for user messages and for assistant messages that cited nothing."""

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
