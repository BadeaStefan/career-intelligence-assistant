"""A missing OPENAI_API_KEY must fail where it can still be explained.

An empty key is not rejected by the OpenAI SDK at construction -- it surfaces
as a 401 on the first request, inside whichever background task happened to
need the model, with nothing in the message naming the variable that was never
set. Settings gives every field a default, so a process that found no env file
starts perfectly happily and only fails there.
"""

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from career_intel.config import Settings
from career_intel.llm.openai_client import MissingCredentialsError, OpenAIClient
from career_intel.models.telemetry import LlmCall


class _DummySchema(BaseModel):
    answer: str = "unused"


def test_construction_without_a_key_does_not_raise(session_factory) -> None:
    """Building a client must stay free of credential requirements.

    enrich_document constructs one unconditionally, "just in case" fakes were
    not injected, and must keep working when it is never used.
    """
    OpenAIClient(session_factory=session_factory, settings=Settings(openai_api_key=""))


async def test_first_real_call_without_a_key_names_the_variable(session_factory) -> None:
    client = OpenAIClient(session_factory=session_factory, settings=Settings(openai_api_key=""))

    with pytest.raises(MissingCredentialsError, match="OPENAI_API_KEY"):
        await client.structured(
            purpose="resume_extraction", system="s", user="u", schema=_DummySchema
        )


async def test_the_failed_call_is_still_recorded(session_factory) -> None:
    """Non-negotiable #5 holds for this failure like any other."""
    client = OpenAIClient(session_factory=session_factory, settings=Settings(openai_api_key=""))

    with pytest.raises(MissingCredentialsError):
        await client.structured(
            purpose="resume_extraction", system="s", user="u", schema=_DummySchema
        )

    async with session_factory() as fresh:
        row = (await fresh.execute(select(LlmCall))).scalar_one()
    assert row.status == "failed"
    assert row.error_type == "MissingCredentialsError"
