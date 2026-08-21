"""Tests for the chat service (Task 18, spec §6).

No network: embeddings and completions come from ``FakeEmbedder``/``FakeLLM``,
retrieval and analysis data come from a real Postgres test database seeded
directly via the ORM, following ``test_fit_engine.py``'s inline-construction
style.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.chat.service import ChatService, create_session, list_messages
from career_intel.constants import EMBEDDING_DIM
from career_intel.llm.fakes import FakeEmbedder, FakeLLM
from career_intel.models import ChatMessage, ChatSession, Chunk, Document, Requirement
from career_intel.models.analysis import FitAnalysis


def _vector(seed: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[seed % EMBEDDING_DIM] = 1.0
    return vector


async def _seed_resume(session: AsyncSession, *, chunk_count: int = 2) -> Document:
    resume = Document(
        kind="resume",
        source="paste",
        raw_text="resume text",
        status="ready",
        extraction_status="ready",
    )
    session.add(resume)
    await session.flush()

    for i in range(chunk_count):
        text = f"resume chunk {i}"
        session.add(
            Chunk(
                document_id=resume.id,
                ordinal=i,
                text=text,
                char_start=0,
                char_end=len(text),
                embedding=_vector(i),
            )
        )
    await session.commit()
    await session.refresh(resume)
    return resume


async def _seed_job(
    session: AsyncSession, *, title: str = "Backend Engineer", company: str = "Acme"
) -> Document:
    job = Document(
        kind="job",
        source="paste",
        raw_text=f"{title} raw text",
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
    session: AsyncSession, *, resume_doc_id: UUID, job_doc_id: UUID
) -> FitAnalysis:
    requirement = Requirement(
        document_id=job_doc_id,
        ordinal=0,
        text="REQUIREMENT-TEXT",
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
        overall_score=0.8,
        summary="Good overall fit.",
        model="gpt-4o-mini",
    )
    session.add(analysis)
    await session.commit()
    return analysis


async def _seed_chat_session(session: AsyncSession, *, job_doc_id: UUID | None) -> ChatSession:
    chat_session = ChatSession(job_doc_id=job_doc_id)
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return chat_session


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


# ---------------------------------------------------------------------------
# Scope: UI state, never inferred from the question
# ---------------------------------------------------------------------------


async def test_scope_comes_from_the_request_not_the_question(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """The question mentions comparing jobs, but scope="job" must still bind
    context to the session's job only. UI state, never prompt inference."""
    await _seed_resume(session)
    job = await _seed_job(session, title="JOB-ONE-TITLE", company="Acme")
    other_job = await _seed_job(session, title="JOB-TWO-TITLE", company="Globex")
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM(text_responses=["Sure, here's a comparison."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    await service.send(chat_session.id, content="compare all my jobs", scope="job")

    assert fake_llm.last_user_prompt is not None
    assert other_job.title not in fake_llm.last_user_prompt


async def test_all_scope_includes_every_cached_analysis(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    resume = await _seed_resume(session)
    job = await _seed_job(session, title="JOB-ONE-TITLE", company="Acme")
    other_job = await _seed_job(session, title="JOB-TWO-TITLE", company="Globex")
    await _seed_ready_analysis(session, resume_doc_id=resume.id, job_doc_id=job.id)
    await _seed_ready_analysis(session, resume_doc_id=resume.id, job_doc_id=other_job.id)
    chat_session = await _seed_chat_session(session, job_doc_id=None)

    fake_llm = FakeLLM(text_responses=["Job one looks like the stronger fit."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    await service.send(chat_session.id, content="which fits best?", scope="all")

    assert fake_llm.last_user_prompt is not None
    assert job.title in fake_llm.last_user_prompt
    assert other_job.title in fake_llm.last_user_prompt


# ---------------------------------------------------------------------------
# Citations: validated the same way as the fit engine's (spec §6/§8)
# ---------------------------------------------------------------------------


async def test_invented_citation_handles_are_dropped(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """A lying LLM cites "c99", which was never offered as a resume-chunk
    handle -- only "c1"/"c2" were, for a 2-chunk resume. Reuses
    validate_handles (Task 12)."""
    await _seed_resume(session, chunk_count=2)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    lying_llm = FakeLLM(text_responses=["You know Python [c99]."])
    service = ChatService(session, llm=lying_llm, embedder=embedder)

    reply = await service.send(chat_session.id, content="Do I know Python?", scope="job")

    assert reply.citations == []


async def test_valid_citation_handles_survive(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """The mirror image of the invented-handle test: a handle that *was*
    offered must survive validation, proving the drop above is really about
    validity and not e.g. every citation always being stripped.

    Also proves the citation is mapped to a real span, not just the bare
    handle string -- and that the handle the model cited was genuinely
    visible in the prompt it was sent, i.e. the offered-handle set and the
    prompt content come from the same retrieval call."""
    resume = await _seed_resume(session, chunk_count=2)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)
    chunk_ids = set(
        (await session.execute(select(Chunk.id).where(Chunk.document_id == resume.id)))
        .scalars()
        .all()
    )

    fake_llm = FakeLLM(text_responses=["You know Python [c1]."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    reply = await service.send(chat_session.id, content="Do I know Python?", scope="job")

    assert "[c1]" in (fake_llm.last_user_prompt or "")

    assert len(reply.citations) == 1
    citation = reply.citations[0]
    assert citation.handle == "c1"
    assert citation.document_id == resume.id
    assert citation.chunk_id in chunk_ids
    assert citation.char_start == 0
    assert citation.char_end == len("resume chunk 0")
    # The cited text travels with the citation. Without it a client holds a
    # chunk id and a span but nothing to *show* -- the citation renders as an
    # inert handle, which is exactly what the fit engine's evidence shape
    # already avoids by carrying its quote directly.
    assert citation.text == "resume chunk 0"


async def test_no_evidence_yields_explicit_absence_not_invention(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session, chunk_count=2)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM()
    fake_llm.queue_text("Your resume shows no Kubernetes experience.")
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    reply = await service.send(chat_session.id, content="Do I know Kubernetes?", scope="job")

    assert reply.citations == []  # an absence claim cites nothing


# ---------------------------------------------------------------------------
# Guardrails (spec §8)
# ---------------------------------------------------------------------------


async def test_system_prompt_carries_the_off_topic_redirect_rule(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM(text_responses=["I can only help with your job search."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    await service.send(chat_session.id, content="write me a poem", scope="job")

    assert fake_llm.last_system_prompt is not None
    assert "only about" in fake_llm.last_system_prompt.lower()
    # Behavioural check runs live in Task 21; unit tests assert the rule ships.


async def test_untrusted_data_notice_names_every_delimited_block(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """The notice has to describe what is actually delimited. Naming only
    "job posting and resume text" while the analysis block is delimited too
    leaves the model to guess which markers it was told about."""
    await _seed_resume(session)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM(text_responses=["Sure."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    await service.send(chat_session.id, content="how do I fit?", scope="job")

    assert fake_llm.last_system_prompt is not None
    notice = fake_llm.last_system_prompt.lower()
    assert "job posting" in notice
    assert "resume" in notice
    assert "analysis" in notice


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def test_message_row_persists_the_scope_it_was_asked_under(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM(text_responses=["Hello!"])
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    await service.send(chat_session.id, content="hi", scope="all")

    row = (
        await session.execute(select(ChatMessage).where(ChatMessage.role == "user"))
    ).scalar_one()
    assert row.scope == "all"
    assert row.content == "hi"

    assistant_row = (
        await session.execute(select(ChatMessage).where(ChatMessage.role == "assistant"))
    ).scalar_one()
    assert assistant_row.scope == "all"
    assert assistant_row.content == "Hello!"

    # created_at is constant across one commit's transaction (Postgres
    # now()), so ordering by created_at alone cannot be trusted to put the
    # question before its own answer -- ordinal is what guarantees it.
    assert row.ordinal < assistant_row.ordinal


async def test_send_raises_for_unknown_session(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    fake_llm = FakeLLM()
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    with pytest.raises(LookupError):
        await service.send(uuid4(), content="hi", scope="all")


async def test_send_raises_for_job_scope_without_a_bound_job(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """A session opened without a job (e.g. straight into "all jobs" scope)
    has no job to scope a "job"-scoped question to -- build_context's own
    validation, surfaced through the service."""
    chat_session = await _seed_chat_session(session, job_doc_id=None)
    fake_llm = FakeLLM()
    service = ChatService(session, llm=fake_llm, embedder=embedder)

    with pytest.raises(ValueError):
        await service.send(chat_session.id, content="how do I fit?", scope="job")


# ---------------------------------------------------------------------------
# Session lifecycle helpers
# ---------------------------------------------------------------------------


async def test_create_session_binds_the_optional_job_doc_id(session: AsyncSession) -> None:
    job = await _seed_job(session)

    created = await create_session(session, job_doc_id=job.id)

    assert created.job_doc_id == job.id


async def test_list_messages_raises_for_unknown_session(session: AsyncSession) -> None:
    with pytest.raises(LookupError):
        await list_messages(session, uuid4())


async def test_list_messages_returns_history_in_order(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    await _seed_resume(session)
    job = await _seed_job(session)
    chat_session = await _seed_chat_session(session, job_doc_id=job.id)

    fake_llm = FakeLLM(text_responses=["First answer.", "Second answer."])
    service = ChatService(session, llm=fake_llm, embedder=embedder)
    await service.send(chat_session.id, content="first question", scope="job")
    await service.send(chat_session.id, content="second question", scope="job")

    history = await list_messages(session, chat_session.id)

    assert [m.content for m in history] == [
        "first question",
        "First answer.",
        "second question",
        "Second answer.",
    ]
