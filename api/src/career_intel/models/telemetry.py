"""``llm_calls`` and ``retrieval_traces`` -- the observability story.

Both tables carry a nullable ``request_id``: background enrichment writes
these rows outside any HTTP request, so there is nothing to bind them to.
"""

from typing import Any

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from career_intel.models.base import Base, TimestampedAt, UUIDPrimaryKey


class LlmCall(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "llm_calls"

    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RetrievalTrace(Base, UUIDPrimaryKey, TimestampedAt):
    __tablename__ = "retrieval_traces"

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
