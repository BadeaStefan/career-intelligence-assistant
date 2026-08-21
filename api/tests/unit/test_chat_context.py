"""Tests for chat context assembly (Task 17, spec §6).

No network: embeddings come from ``FakeEmbedder``, retrieval and analysis
data come from a real Postgres test database seeded directly via the ORM,
following ``test_fit_engine.py``'s inline-construction style.
"""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.chat.context import (
    _DOCUMENT_DELIMITER,
    MAX_HISTORY_TOKENS,
    MAX_HISTORY_TURNS,
    Turn,
    build_context,
    select_history,
)
from career_intel.constants import EMBEDDING_DIM
from career_intel.llm.fakes import FakeEmbedder
from career_intel.llm.tokens import count_tokens
from career_intel.models import Chunk, Document, Requirement
from career_intel.models.analysis import FitAnalysis, RequirementMatch


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


async def _seed_resume(session: AsyncSession, *, raw_text: str = "resume text") -> Document:
    resume = Document(
        kind="resume",
        source="paste",
        raw_text=raw_text,
        status="ready",
        extraction_status="ready",
    )
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


async def _seed_chunk(
    session: AsyncSession, *, document_id: UUID, text: str, ordinal: int = 0
) -> Chunk:
    chunk = Chunk(
        document_id=document_id,
        ordinal=ordinal,
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vector(ordinal),
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)
    return chunk


async def _seed_job(
    session: AsyncSession, *, title: str, company: str, raw_text: str
) -> Document:
    job = Document(
        kind="job",
        source="paste",
        raw_text=raw_text,
        title=title,
        company=company,
        status="ready",
        extraction_status="ready",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _seed_ready_analysis(
    session: AsyncSession,
    *,
    resume_doc_id: UUID,
    job_doc_id: UUID,
    requirement_text: str,
    verdict: str = "strong",
    rationale: str = "matches directly",
    summary: str = "Good overall fit.",
    overall_score: float = 0.8,
) -> FitAnalysis:
    requirement = Requirement(
        document_id=job_doc_id,
        ordinal=0,
        text=requirement_text,
        importance="required",
        category="general",
        embedding=_vector(0),
    )
    session.add(requirement)
    await session.flush()

    analysis = FitAnalysis(
        resume_doc_id=resume_doc_id,
        job_doc_id=job_doc_id,
        status="ready",
        overall_score=overall_score,
        summary=summary,
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.flush()

    session.add(
        RequirementMatch(
            fit_analysis_id=analysis.id,
            requirement_id=requirement.id,
            verdict=verdict,
            rationale=rationale,
        )
    )
    await session.commit()
    await session.refresh(analysis)
    return analysis


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


# ---------------------------------------------------------------------------
# select_history
# ---------------------------------------------------------------------------


def test_select_history_returns_empty_for_no_turns() -> None:
    assert select_history([]) == []


def test_select_history_caps_at_max_turns() -> None:
    turns = [Turn(role="user", content=f"turn {i}") for i in range(MAX_HISTORY_TURNS + 2)]

    result = select_history(turns)

    assert len(result) == MAX_HISTORY_TURNS
    # the most recent MAX_HISTORY_TURNS survive, in original order
    assert result == turns[-MAX_HISTORY_TURNS:]


def test_select_history_drops_oldest_first_when_over_token_budget() -> None:
    # Five turns, well under the MAX_HISTORY_TURNS cap, but individually
    # large enough that the full set exceeds MAX_HISTORY_TOKENS.
    big_content = "word " * 400
    turns = [Turn(role="user", content=f"{big_content}{i}") for i in range(5)]
    assert count_tokens("".join(t.content for t in turns)) > MAX_HISTORY_TOKENS

    result = select_history(turns)

    assert turns[-1] in result, "the most recent turn must survive"
    assert turns[0] not in result, "the oldest turn must be dropped first"
    assert sum(count_tokens(t.content) for t in result) <= MAX_HISTORY_TOKENS
    # what remains is a contiguous suffix of the original list
    assert result == turns[-len(result) :]


def test_select_history_truncates_rather_than_drops_a_lone_oversized_turn() -> None:
    huge = Turn(role="user", content="word " * 3000)
    assert count_tokens(huge.content) > MAX_HISTORY_TOKENS

    result = select_history([huge])

    assert len(result) == 1, "a single oversized turn must be truncated, never dropped"
    assert result[0].role == "user"
    assert count_tokens(result[0].content) <= MAX_HISTORY_TOKENS
    assert len(result[0].content) < len(huge.content)


def test_select_history_truncates_most_recent_turn_when_it_alone_exceeds_budget() -> None:
    """A follow-up must never lose its own question: even when an earlier
    turn is dropped to make room, if the most recent turn alone still
    exceeds the budget, it is truncated -- not dropped -- so the caller's
    current question always survives."""
    small = Turn(role="assistant", content="ok")
    huge = Turn(role="user", content="word " * 3000)

    result = select_history([small, huge])

    assert len(result) == 1
    assert result[0].role == "user", "the most recent turn's role must be preserved"
    assert count_tokens(result[0].content) <= MAX_HISTORY_TOKENS


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


async def test_scope_job_includes_only_that_jobs_spec_and_analysis(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    resume = await _seed_resume(session)
    job_one = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="JOB-ONE-UNIQUE-TEXT"
    )
    job_two = await _seed_job(
        session, title="Platform Engineer", company="Globex", raw_text="JOB-TWO-UNIQUE-TEXT"
    )
    await _seed_ready_analysis(
        session,
        resume_doc_id=resume.id,
        job_doc_id=job_one.id,
        requirement_text="REQUIREMENT-ONE-UNIQUE",
    )
    await _seed_ready_analysis(
        session,
        resume_doc_id=resume.id,
        job_doc_id=job_two.id,
        requirement_text="REQUIREMENT-TWO-UNIQUE",
    )

    context = await build_context(
        session,
        scope="job",
        job_doc_id=job_one.id,
        question="How well do I fit?",
        history=[],
        embedder=embedder,
    )

    assert "JOB-ONE-UNIQUE-TEXT" in context.text
    assert "REQUIREMENT-ONE-UNIQUE" in context.text
    assert "JOB-TWO-UNIQUE-TEXT" not in context.text
    assert "REQUIREMENT-TWO-UNIQUE" not in context.text
    assert "Globex" not in context.text


async def test_scope_all_includes_every_cached_analysis(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    resume = await _seed_resume(session)
    job_one = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="job one raw text"
    )
    job_two = await _seed_job(
        session, title="Platform Engineer", company="Globex", raw_text="job two raw text"
    )
    await _seed_ready_analysis(
        session,
        resume_doc_id=resume.id,
        job_doc_id=job_one.id,
        requirement_text="REQUIREMENT-ONE-UNIQUE",
        summary="Summary for job one.",
    )
    await _seed_ready_analysis(
        session,
        resume_doc_id=resume.id,
        job_doc_id=job_two.id,
        requirement_text="REQUIREMENT-TWO-UNIQUE",
        summary="Summary for job two.",
    )

    context = await build_context(
        session,
        scope="all",
        job_doc_id=None,
        question="Which job am I strongest for?",
        history=[],
        embedder=embedder,
    )

    assert "Acme" in context.text
    assert "Globex" in context.text
    assert "REQUIREMENT-ONE-UNIQUE" in context.text
    assert "REQUIREMENT-TWO-UNIQUE" in context.text
    assert "Summary for job one." in context.text
    assert "Summary for job two." in context.text


async def test_document_text_is_delimited(session: AsyncSession, embedder: FakeEmbedder) -> None:
    resume = await _seed_resume(session)
    await _seed_chunk(session, document_id=resume.id, text="CHUNK-UNIQUE-TEXT")
    job = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="JOB-SPEC-UNIQUE-TEXT"
    )

    context = await build_context(
        session,
        scope="job",
        job_doc_id=job.id,
        question="What's my strongest match?",
        history=[],
        embedder=embedder,
    )

    assert f"{_DOCUMENT_DELIMITER}\nJOB-SPEC-UNIQUE-TEXT\n{_DOCUMENT_DELIMITER}" in context.text
    assert f"{_DOCUMENT_DELIMITER}\nCHUNK-UNIQUE-TEXT\n{_DOCUMENT_DELIMITER}" in context.text


async def test_returned_chunks_are_the_same_ones_rendered_into_the_text(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """Task 18 offers ``context.chunks`` as citation handles -- they must be
    exactly what the model was shown, not a second, independently-retrieved
    set that only happens to match by coincidence."""
    resume = await _seed_resume(session)
    await _seed_chunk(session, document_id=resume.id, text="CHUNK-UNIQUE-TEXT")
    job = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="job raw text"
    )

    context = await build_context(
        session,
        scope="job",
        job_doc_id=job.id,
        question="What's my strongest match?",
        history=[],
        embedder=embedder,
    )

    assert context.resume_doc_id == resume.id
    assert len(context.chunks) == 1
    chunk = context.chunks[0]
    assert chunk.text == "CHUNK-UNIQUE-TEXT"
    # The handle labelling the chunk in the prompt text is the same handle
    # on the returned candidate -- a caller can offer exactly this handle.
    assert f"[{chunk.handle}]" in context.text


async def test_build_context_includes_history_and_question(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session)
    job = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="job raw text"
    )

    context = await build_context(
        session,
        scope="job",
        job_doc_id=job.id,
        question="QUESTION-UNIQUE-MARKER",
        history=[
            Turn(role="user", content="EARLIER-USER-TURN"),
            Turn(role="assistant", content="EARLIER-ASSISTANT-TURN"),
        ],
        embedder=embedder,
    )

    assert "EARLIER-USER-TURN" in context.text
    assert "EARLIER-ASSISTANT-TURN" in context.text
    assert "QUESTION-UNIQUE-MARKER" in context.text


async def test_scope_job_without_job_doc_id_raises(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session)

    with pytest.raises(ValueError):
        await build_context(
            session,
            scope="job",
            job_doc_id=None,
            question="anything",
            history=[],
            embedder=embedder,
        )


async def test_scope_job_with_no_analysis_yet_still_includes_job_spec(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """A job that hasn't been analysed yet (or failed extraction) is still
    answerable via chunk RAG over the job spec -- chat degrades gracefully
    rather than erroring, mirroring spec §3's chunk-RAG fallback."""
    await _seed_resume(session)
    job = await _seed_job(
        session, title="Backend Engineer", company="Acme", raw_text="UNANALYSED-JOB-TEXT"
    )

    context = await build_context(
        session,
        scope="job",
        job_doc_id=job.id,
        question="How do I match?",
        history=[],
        embedder=embedder,
    )

    assert "UNANALYSED-JOB-TEXT" in context.text
