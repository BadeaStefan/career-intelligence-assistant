"""Tests for the chat HTTP surface (Task 18's routes).

Everything else about chat is covered at the service layer
(test_chat_service.py). What only exists at this layer, and so can only break
here, is:

- ``LookupError -> 404`` and ``ValueError -> 400``. Those translations live
  in the handler; the service just raises.
- ``Citation.model_validate(c)`` on the way back out of the ``citations``
  jsonb column. Nothing round-trips a persisted citation through the
  response model anywhere else, so a field added to ``Citation`` without a
  matching write path is a live 500 that no service-layer test would see.

Seeding happens on a throwaway engine/session, never the ``session``
fixture's cached one, because these tests also drive ``client`` (a
``TestClient`` running the app in its own thread with its own event loop) --
the same reason test_prep_route.py and test_analyses_route.py do it.

``routes/chat.py`` builds a real ``OpenAIClient`` per request and hands it in
as *both* the ``LLMClient`` and the ``Embedder``, so the autouse fixture
below monkeypatches that class reference with a fake that satisfies both
protocols. Stubbing at that boundary is the repo's pattern for route tests
over endpoints that construct their own client (non-negotiable #2).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_intel.constants import EMBEDDING_DIM
from career_intel.llm.fakes import FakeEmbedder, FakeLLM
from career_intel.models import Chunk, Document
from tests.conftest import TEST_DATABASE_URL

MISSING_ID = "00000000-0000-0000-0000-000000000000"
CHUNK_TEXT = "Built an ingestion pipeline in production Python"


class FakeLLMAndEmbedder(FakeLLM):
    """One object standing in for ``OpenAIClient``, which is both.

    ``routes/chat.py`` passes the single client it builds as ``llm=`` and
    ``embedder=`` alike -- a fake that only satisfied ``LLMClient`` would
    fail on ``build_context``'s very first line.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._embedder = FakeEmbedder()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embedder.embed(texts)


@pytest.fixture
def fake_llm() -> FakeLLMAndEmbedder:
    return FakeLLMAndEmbedder(text_responses=["You have shipped production Python [c1]."])


@pytest.fixture(autouse=True)
def _stub_openai_client(monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLMAndEmbedder) -> None:
    monkeypatch.setattr("career_intel.api.routes.chat.OpenAIClient", lambda **kwargs: fake_llm)


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


@asynccontextmanager
async def _throwaway_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def job_doc_id() -> uuid.UUID:
    """A resume with one citable chunk, plus a job to scope to."""
    async with _throwaway_session() as session:
        resume = Document(
            kind="resume",
            source="paste",
            raw_text=CHUNK_TEXT,
            status="ready",
            extraction_status="ready",
        )
        session.add(resume)
        await session.flush()
        session.add(
            Chunk(
                document_id=resume.id,
                ordinal=0,
                text=CHUNK_TEXT,
                char_start=0,
                char_end=len(CHUNK_TEXT),
                embedding=_vector(0),
            )
        )

        job = Document(
            kind="job",
            source="paste",
            raw_text="Senior Backend Engineer, Python required",
            title="Senior Backend Engineer",
            company="Acme",
            status="ready",
            extraction_status="ready",
        )
        session.add(job)
        await session.commit()
        return job.id


def _open_session(client: TestClient, job_doc_id: uuid.UUID | None) -> str:
    body = client.post(
        "/chat/sessions",
        json={"job_doc_id": str(job_doc_id) if job_doc_id else None},
    )
    assert body.status_code == 201
    return str(body.json()["id"])


def test_create_session_returns_an_id_the_client_can_post_to(
    client: TestClient, job_doc_id: uuid.UUID
) -> None:
    response = client.post("/chat/sessions", json={"job_doc_id": str(job_doc_id)})

    assert response.status_code == 201
    assert uuid.UUID(response.json()["id"])


def test_create_session_without_a_job_is_allowed(client: TestClient) -> None:
    """A session opened straight into "all jobs" scope binds no job."""
    assert client.post("/chat/sessions", json={}).status_code == 201


def test_send_message_answers_with_validated_citations(
    client: TestClient, job_doc_id: uuid.UUID
) -> None:
    session_id = _open_session(client, job_doc_id)

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Do I know Python?", "scope": "job"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"].startswith("You have shipped production Python")
    assert len(body["citations"]) == 1
    assert body["citations"][0]["handle"] == "c1"
    assert body["citations"][0]["text"] == CHUNK_TEXT


def test_citations_round_trip_out_of_the_jsonb_column(
    client: TestClient, job_doc_id: uuid.UUID
) -> None:
    """The GET deserialises ``citations`` back through ``Citation``. A field
    added to that model without a matching write path 500s here and nowhere
    else -- the POST's own response is built from live objects, never from
    the persisted jsonb."""
    session_id = _open_session(client, job_doc_id)
    posted = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Do I know Python?", "scope": "job"},
    ).json()

    response = client.get(f"/chat/sessions/{session_id}/messages")

    assert response.status_code == 200
    history = response.json()
    assert [row["role"] for row in history] == ["user", "assistant"]
    assert history[0]["citations"] == []
    assert history[1]["citations"] == posted["citations"]
    assert history[1]["scope"] == "job"


def test_send_message_to_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/chat/sessions/{MISSING_ID}/messages",
        json={"content": "anything", "scope": "all"},
    )

    assert response.status_code == 404


def test_get_messages_for_unknown_session_returns_404(client: TestClient) -> None:
    """404, not an empty list: an id that was never created is a different
    answer from a session nobody has spoken in yet."""
    assert client.get(f"/chat/sessions/{MISSING_ID}/messages").status_code == 404


def test_job_scope_without_a_bound_job_returns_400(client: TestClient) -> None:
    """The session exists, so this is a bad request, not a missing one."""
    session_id = _open_session(client, None)

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "how do I fit?", "scope": "job"},
    )

    assert response.status_code == 400


def test_unknown_scope_is_rejected_before_any_llm_call(
    client: TestClient, job_doc_id: uuid.UUID, fake_llm: FakeLLMAndEmbedder
) -> None:
    session_id = _open_session(client, job_doc_id)

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "hi", "scope": "everything"},
    )

    assert response.status_code == 422
    assert fake_llm.call_count == 0
