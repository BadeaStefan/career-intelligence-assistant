"""In-memory Embedder/LLMClient for tests and offline dev. No network."""

import hashlib
import random
from typing import Any, TypeVar

from pydantic import BaseModel

from career_intel.constants import EMBEDDING_DIM

T = TypeVar("T", bound=BaseModel)


class FakeEmbedder:
    """Deterministic hash-based vectors.

    Same text always yields the same vector, so tests can assert similarity
    ordering without ever calling OpenAI.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self._dim)]


class FakeLLM:
    """Returns queued canned responses instead of calling OpenAI.

    ``structured`` validates each queued payload against the schema the
    caller asked for -- a payload that doesn't fit raises
    ``pydantic.ValidationError``, letting tests exercise the same
    malformed-response retry path a real schema-validation failure would
    trigger.
    """

    def __init__(
        self,
        *,
        structured_responses: list[dict[str, Any]] | None = None,
        text_responses: list[str] | None = None,
    ) -> None:
        self._structured_queue = list(structured_responses or [])
        self._text_queue = list(text_responses or [])
        self.calls: list[dict[str, str]] = []

    async def structured(self, *, purpose: str, system: str, user: str, schema: type[T]) -> T:
        self.calls.append(
            {"kind": "structured", "purpose": purpose, "system": system, "user": user}
        )
        if not self._structured_queue:
            raise RuntimeError("FakeLLM: no queued structured response left")
        payload = self._structured_queue.pop(0)
        return schema.model_validate(payload)

    async def text(self, *, purpose: str, system: str, user: str) -> str:
        self.calls.append({"kind": "text", "purpose": purpose, "system": system, "user": user})
        if not self._text_queue:
            raise RuntimeError("FakeLLM: no queued text response left")
        return self._text_queue.pop(0)

    @property
    def last_user_prompt(self) -> str | None:
        return self.calls[-1]["user"] if self.calls else None

    @property
    def last_system_prompt(self) -> str | None:
        return self.calls[-1]["system"] if self.calls else None

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def queue_text(self, text: str) -> None:
        self._text_queue.append(text)
