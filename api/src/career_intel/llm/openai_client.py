"""The real Embedder/LLMClient implementation, backed by the OpenAI SDK.

Every call writes its own ``llm_calls`` row in its own short-lived session,
committed immediately -- never inside a caller's transaction. A shared
injected session would autobegin a transaction on the first telemetry write
and hold it open across the network call that follows, exactly the ordering
non-negotiable #4 forbids; a failed batch would also roll back the row
describing the failure.
"""

import time
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_intel.config import Settings
from career_intel.constants import MODEL_PRICE_PER_MILLION_TOKENS
from career_intel.models.telemetry import LlmCall
from career_intel.observability import request_id_var

T = TypeVar("T", bound=BaseModel)


class MissingCredentialsError(Exception):
    """Raised when a real call is attempted with no API key configured.

    The SDK accepts an empty key at construction and fails with a 401 on the
    first request, from inside whichever background task needed the model and
    with nothing naming the variable that was never set. Settings gives every
    field a default, so a process that found no env file starts cleanly and
    only fails there.
    """


def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = MODEL_PRICE_PER_MILLION_TOKENS.get(model, {"prompt": 0.0, "completion": 0.0})
    return (prompt_tokens * price["prompt"] + completion_tokens * price["completion"]) / 1_000_000


class OpenAIClient:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        raw: AsyncOpenAI | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._raw_override = raw
        self._lazy_raw: AsyncOpenAI | None = None

    @property
    def _raw(self) -> AsyncOpenAI:
        # Built lazily, on first real call, rather than in __init__: a
        # client constructed but never used (the common shape when
        # enrich_document builds one "just in case" fakes weren't passed)
        # must not require live credentials to exist.
        if self._raw_override is not None:
            return self._raw_override
        if self._lazy_raw is None:
            # Checked here rather than in __init__ for the same reason the
            # client is built here: this is the first moment credentials are
            # actually required.
            if not self._settings.openai_api_key:
                raise MissingCredentialsError(
                    "OPENAI_API_KEY is not set, so no OpenAI call can be made."
                    " Set it in api/.env for a local venv, or in the .env that"
                    " docker compose reads."
                )
            self._lazy_raw = AsyncOpenAI(api_key=self._settings.openai_api_key)
        return self._lazy_raw

    async def structured(self, *, purpose: str, system: str, user: str, schema: type[T]) -> T:
        start = time.monotonic()
        try:
            completion = await self._raw.beta.chat.completions.parse(
                model=self._settings.llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=schema,
            )
        except Exception as exc:
            await self._record_failure(purpose, self._settings.llm_model, start, exc)
            raise
        latency_ms = int((time.monotonic() - start) * 1000)
        assert completion.usage is not None, "non-streaming completions always report usage"

        await self._record_call(
            purpose=purpose,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
            latency_ms=latency_ms,
        )
        parsed = completion.choices[0].message.parsed
        assert parsed is not None, "structured outputs guarantee a parsed result on success"
        return parsed

    async def text(self, *, purpose: str, system: str, user: str) -> str:
        start = time.monotonic()
        try:
            completion = await self._raw.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            await self._record_failure(purpose, self._settings.llm_model, start, exc)
            raise
        latency_ms = int((time.monotonic() - start) * 1000)
        assert completion.usage is not None, "non-streaming completions always report usage"

        await self._record_call(
            purpose=purpose,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
            latency_ms=latency_ms,
        )
        content = completion.choices[0].message.content
        assert content is not None, "a text-only chat completion always has content"
        return content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        start = time.monotonic()
        try:
            response = await self._raw.embeddings.create(
                model=self._settings.embedding_model, input=texts
            )
        except Exception as exc:
            await self._record_failure("embedding", self._settings.embedding_model, start, exc)
            raise
        latency_ms = int((time.monotonic() - start) * 1000)

        await self._record_call(
            purpose="embedding",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=0,
            latency_ms=latency_ms,
            model=self._settings.embedding_model,
        )
        return [item.embedding for item in response.data]

    async def _record_call(
        self,
        *,
        purpose: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        model: str | None = None,
    ) -> None:
        model = model or self._settings.llm_model
        row = LlmCall(
            purpose=purpose,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=_cost_usd(model, prompt_tokens, completion_tokens),
            status="succeeded",
            error_type=None,
            request_id=request_id_var.get(),
        )
        async with self._session_factory() as session:
            session.add(row)
            await session.commit()

    async def _record_failure(
        self, purpose: str, model: str, start: float, error: Exception
    ) -> None:
        row = LlmCall(
            purpose=purpose,
            model=model,
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=int((time.monotonic() - start) * 1000),
            cost_usd=None,
            status="failed",
            error_type=type(error).__name__[:128],
            request_id=request_id_var.get(),
        )
        async with self._session_factory() as session:
            session.add(row)
            await session.commit()
