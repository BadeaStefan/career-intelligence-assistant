"""Every OpenAIClient call must record a committed llm_calls row.

Uses a local throwaway schema rather than a real extraction schema: Task 6
(this file) must not depend on Task 9's ingest/schemas.py, which does not
exist yet -- only Task 9 depends on Task 6, never the other way around.
"""

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from career_intel.llm.openai_client import OpenAIClient
from career_intel.models.telemetry import LlmCall
from career_intel.observability import request_id_var


class _DummySchema(BaseModel):
    answer: str = "unused"


async def test_every_structured_call_records_a_committed_llm_call_row(
    session_factory, settings, openai_stub
):
    client = OpenAIClient(session_factory=session_factory, settings=settings, raw=openai_stub)
    await client.structured(purpose="resume_extraction", system="s", user="u", schema=_DummySchema)

    # A *fresh* session must see the row: telemetry commits immediately in its
    # own session, never inside a caller's transaction.
    async with session_factory() as fresh:
        row = (await fresh.execute(select(LlmCall))).scalar_one()
    assert row.purpose == "resume_extraction"
    assert row.prompt_tokens > 0
    assert row.latency_ms >= 0
    assert row.cost_usd > 0
    assert row.status == "succeeded"
    assert row.error_type is None


async def test_llm_call_row_carries_request_id_when_in_request_context(
    session_factory, settings, openai_stub
):
    token = request_id_var.set("req-42")
    try:
        client = OpenAIClient(session_factory=session_factory, settings=settings, raw=openai_stub)
        await client.text(purpose="chat", system="s", user="u")
    finally:
        request_id_var.reset(token)

    async with session_factory() as fresh:
        row = (await fresh.execute(select(LlmCall))).scalar_one()
    assert row.request_id == "req-42"


@pytest.mark.parametrize("call_kind", ["structured", "text", "embedding"])
async def test_failed_provider_call_records_failure_without_inventing_usage(
    session_factory, settings, openai_stub, call_kind
):
    async def fail(**_kwargs):
        raise RuntimeError("provider unavailable")

    client = OpenAIClient(session_factory=session_factory, settings=settings, raw=openai_stub)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        if call_kind == "structured":
            openai_stub.beta.chat.completions.parse = fail
            await client.structured(
                purpose="resume_extraction", system="s", user="u", schema=_DummySchema
            )
        elif call_kind == "text":
            openai_stub.chat.completions.create = fail
            await client.text(purpose="chat", system="s", user="u")
        else:
            openai_stub.embeddings.create = fail
            await client.embed(["text"])

    async with session_factory() as fresh:
        row = (await fresh.execute(select(LlmCall))).scalar_one()
    assert row.status == "failed"
    assert row.error_type == "RuntimeError"
    assert row.prompt_tokens is None
    assert row.completion_tokens is None
    assert row.cost_usd is None
    assert row.latency_ms >= 0
