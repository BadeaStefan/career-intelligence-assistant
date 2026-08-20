"""A stand-in for the raw OpenAI SDK client.

Exercises ``OpenAIClient``'s telemetry-writing behaviour without a real
network call. Only the surface ``OpenAIClient`` actually calls is faked.
"""

from types import SimpleNamespace
from typing import Any


class FakeOpenAIRaw:
    def __init__(
        self,
        *,
        prompt_tokens: int = 12,
        completion_tokens: int = 4,
        text: str = "canned response",
    ) -> None:
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._text = text
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.embeddings = SimpleNamespace(create=self._embed)

    def _usage(self) -> SimpleNamespace:
        return SimpleNamespace(
            prompt_tokens=self._prompt_tokens, completion_tokens=self._completion_tokens
        )

    async def _parse(
        self, *, model: str, messages: list[dict[str, str]], response_format: type[Any]
    ) -> Any:
        parsed = response_format.model_construct()
        message = SimpleNamespace(parsed=parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self._usage())

    async def _create(self, *, model: str, messages: list[dict[str, str]]) -> Any:
        message = SimpleNamespace(content=self._text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self._usage())

    async def _embed(self, *, model: str, input: list[str]) -> Any:
        data = [SimpleNamespace(embedding=[0.0]) for _ in input]
        usage = SimpleNamespace(prompt_tokens=self._prompt_tokens)
        return SimpleNamespace(data=data, usage=usage)
