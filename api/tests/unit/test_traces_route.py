"""HTTP contract for request-scoped LLM and retrieval telemetry."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_intel.models import LlmCall, RetrievalTrace
from tests.conftest import TEST_DATABASE_URL


@dataclass(frozen=True)
class SeededTrace:
    request_id: str
    raw_resume_text: str


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
async def seeded_traces() -> SeededTrace:
    seed = SeededTrace(
        request_id="trace-request-42",
        raw_resume_text="PRIVATE RESUME: Jane Example worked at Secret Corp.",
    )
    async with _throwaway_session() as session:
        session.add_all(
            [
                LlmCall(
                    purpose="chat",
                    model="gpt-4o-mini",
                    prompt_tokens=120,
                    completion_tokens=35,
                    latency_ms=245,
                    cost_usd=0.000039,
                    status="succeeded",
                    request_id=seed.request_id,
                ),
                LlmCall(
                    purpose="chat",
                    model="gpt-4o-mini",
                    prompt_tokens=999,
                    completion_tokens=99,
                    latency_ms=999,
                    cost_usd=0.5,
                    status="succeeded",
                    request_id="some-other-request",
                ),
                RetrievalTrace(
                    request_id=seed.request_id,
                    query="nearest_chunks document_id=00000000-0000-0000-0000-000000000001",
                    results={
                        "candidates": [
                            {
                                "id": "chunk-1",
                                "handle": "c1",
                                "score": 0.91,
                                # Defence in depth: even a legacy/bad writer
                                # must not make raw PII cross this read boundary.
                                "text": seed.raw_resume_text,
                            },
                            {"id": "chunk-2", "handle": "c2", "score": 0.78},
                        ]
                    },
                ),
            ]
        )
        await session.commit()
    return seed


@pytest_asyncio.fixture
async def seeded_failed_call() -> SeededTrace:
    seed = SeededTrace(request_id="failed-request-7", raw_resume_text="PRIVATE RESUME")
    async with _throwaway_session() as session:
        session.add(
            LlmCall(
                purpose="chat",
                model="gpt-4o-mini",
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=87,
                cost_usd=None,
                status="failed",
                error_type="RateLimitError",
                request_id=seed.request_id,
            )
        )
        await session.commit()
    return seed


def test_traces_endpoint_groups_calls_and_retrievals_by_request_id(
    client: TestClient, seeded_traces: SeededTrace
) -> None:
    response = client.get(f"/traces/{seeded_traces.request_id}")
    assert response.status_code == 200
    body = response.json()
    call = body["llm_calls"][0]
    assert call["purpose"] and call["prompt_tokens"] > 0 and call["cost_usd"] > 0
    assert body["retrievals"][0]["results"]["candidates"]


def test_other_requests_traces_are_not_returned(
    client: TestClient, seeded_traces: SeededTrace
) -> None:
    body = client.get(f"/traces/{seeded_traces.request_id}").json()
    assert all(call["request_id"] == seeded_traces.request_id for call in body["llm_calls"])
    assert all(
        retrieval["request_id"] == seeded_traces.request_id
        for retrieval in body["retrievals"]
    )


def test_trace_payload_never_contains_raw_document_text(
    client: TestClient, seeded_traces: SeededTrace
) -> None:
    body = client.get(f"/traces/{seeded_traces.request_id}").text
    assert seeded_traces.raw_resume_text not in body


def test_failed_call_trace_has_status_without_invented_usage(
    client: TestClient, seeded_failed_call: SeededTrace
) -> None:
    call = client.get(f"/traces/{seeded_failed_call.request_id}").json()["llm_calls"][0]
    assert call["status"] == "failed"
    assert call["error_type"]
    assert call["prompt_tokens"] is None
    assert call["cost_usd"] is None
