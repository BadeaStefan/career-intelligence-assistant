"""Provider-agnostic seams for embeddings and LLM calls.

Everything above this module -- ingest, analysis, chat, prep -- depends only
on these Protocols, never on the OpenAI SDK directly. Tests inject
``FakeEmbedder``/``FakeLLM`` (``llm/fakes.py``); production wiring builds
``OpenAIClient`` (``llm/openai_client.py``), which satisfies both.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class LLMClient(Protocol):
    async def structured(
        self, *, purpose: str, system: str, user: str, schema: type[T]
    ) -> T: ...

    async def text(self, *, purpose: str, system: str, user: str) -> str: ...
