"""Chat context assembly (Task 17, spec §6).

``build_context`` is a pure read layer: it never opens a write transaction
and never calls an LLM itself. Task 18 passes its return value straight into
a chat completion.

Two scopes, chosen by the caller (a UI toggle, never inferred -- spec §6:
"Anything that can be UI state must never be a prompt inference"):

- ``"job"``: the selected job's full spec plus its cached fit analysis.
- ``"all"``: every job's identity plus its cached fit analysis, no full job
  specs -- this is what keeps the "all jobs" scope's budget near the ~4000
  tokens spec §6 budgets for it instead of concatenating every posting.

Both scopes also carry top-k resume chunks (retrieved via
``analysis.retrieval.nearest_chunks``, scoped to the resume document by SQL,
not by prompt instruction -- non-negotiable #11) and the last few
conversation turns (``select_history``).

Ordering matters here for a reason that isn't obvious from reading top to
bottom: ``embedder.embed`` stands in for a real OpenAI call in production,
so it runs *before* any read on ``session`` -- never interleaved with one.
That keeps this function from ever holding a transaction open on the
caller's session while awaiting a network call (non-negotiable #4), without
this read-only function needing to close a session it doesn't own.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.analysis.retrieval import ChunkCandidate, nearest_chunks
from career_intel.llm.protocol import Embedder
from career_intel.llm.tokens import count_tokens
from career_intel.models import Document, Requirement
from career_intel.models.analysis import FitAnalysis, RequirementMatch

MAX_HISTORY_TURNS = 8
MAX_HISTORY_TOKENS = 1500

# Identical text to career_intel.ingest.extraction's delimiter -- Task 18's
# system prompt describes one marker meaning "untrusted document data" that
# covers every document-derived block that lands in a prompt, whether it
# came from ingest-time extraction or here at chat time. Mirrored locally
# rather than imported: chat depending on ingest would read backwards --
# ingest is a write-time pipeline concern, chat is a read-time consumer of
# its output, and the two should not need each other's internals to change
# independently. The delimiter *text* is kept identical on purpose.
_DOCUMENT_DELIMITER = "-----DOCUMENT-----"


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatContext:
    """``build_context``'s return value.

    ``text`` is the assembled prompt, ready to hand an LLM as-is. ``chunks``
    is the *same* ``ChunkCandidate`` list rendered into ``text`` -- returned
    alongside it, not re-fetched, so a caller offering citation handles to a
    model is guaranteed to offer exactly the chunks the model actually read
    rather than a second, independently-retrieved (and only incidentally
    identical) set (Task 18). ``resume_doc_id`` is the resume those chunks
    came from, or ``None`` if no resume exists yet -- carried here so a
    caller can attach a citation's owning document without another query.
    """

    text: str
    chunks: list[ChunkCandidate]
    resume_doc_id: UUID | None


def _delimit(raw_text: str) -> str:
    return f"{_DOCUMENT_DELIMITER}\n{raw_text}\n{_DOCUMENT_DELIMITER}"


def _history_tokens(turns: Sequence[Turn]) -> int:
    return sum(count_tokens(turn.content) for turn in turns)


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Shrink ``text`` to fit within ``max_tokens``, cut on a word boundary.

    Keeps the *prefix*: for a chat turn, the start of what someone said is
    usually the part a follow-up refers back to, more often than the end.
    """
    if count_tokens(text) <= max_tokens:
        return text

    # Binary search on character length for the longest prefix that still
    # fits the budget -- tiktoken has no cheap way to count "the first N
    # tokens' worth of characters" directly.
    lo, hi = 0, len(text)
    fit = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid]
        if count_tokens(candidate) <= max_tokens:
            fit = candidate
            lo = mid + 1
        else:
            hi = mid - 1

    boundary = fit.rfind(" ")
    if boundary > 0:
        fit = fit[:boundary]
    return fit.rstrip() + " …"


def select_history(turns: Sequence[Turn]) -> list[Turn]:
    """Cap history at ``MAX_HISTORY_TURNS``, then drop oldest turns until
    what remains fits ``MAX_HISTORY_TOKENS``.

    Dropped turns are never summarised: summarisation is a second LLM call
    in the hot path that can itself hallucinate, and at this corpus size a
    session long enough to need it is already an outlier (spec §6).

    The most recent turn always survives. If it alone exceeds the token
    budget, its *content* is truncated rather than the turn being dropped --
    a follow-up like "what about that second gap?" must never lose its own
    question.
    """
    capped = list(turns[-MAX_HISTORY_TURNS:])

    while len(capped) > 1 and _history_tokens(capped) > MAX_HISTORY_TOKENS:
        capped.pop(0)

    if capped and _history_tokens(capped) > MAX_HISTORY_TOKENS:
        only = capped[0]
        capped[0] = Turn(
            role=only.role, content=_truncate_to_budget(only.content, MAX_HISTORY_TOKENS)
        )

    return capped


def _format_history(turns: Sequence[Turn]) -> str:
    if not turns:
        return ""
    lines = [f"{turn.role}: {turn.content}" for turn in turns]
    return "Conversation so far:\n" + "\n".join(lines)


def _format_job_spec(job: Document) -> str:
    header = f"Job: {job.title or 'Untitled role'} at {job.company or 'unknown company'}"
    return f"{header}\n{_delimit(job.raw_text)}"


def _format_analysis(
    job: Document,
    analysis: FitAnalysis | None,
    matches: Sequence[tuple[RequirementMatch, Requirement]],
) -> str:
    header = f"{job.title or 'Untitled role'} at {job.company or 'unknown company'}"
    if analysis is None or analysis.status != "ready":
        return f"{header}: no fit analysis yet"

    score_pct = round((analysis.overall_score or 0.0) * 100)
    lines = [f"{header} -- fit score {score_pct}%"]
    if analysis.summary:
        lines.append(analysis.summary)
    for match, requirement in matches:
        lines.append(
            f"- [{match.verdict}] ({requirement.importance}) {requirement.text}: "
            f"{match.rationale}"
        )
    return "\n".join(lines)


def _format_chunks(chunks: Sequence[ChunkCandidate]) -> str:
    if not chunks:
        return ""
    # Each chunk is labelled with its retrieval handle (e.g. "[c1]") right
    # before its delimited text -- Task 18's chat service asks the model to
    # cite claims using this exact handle, so the handle has to be visible
    # in the prompt, inside the same untrusted-data-delimited block as the
    # text it labels (not a separate, undelimited block elsewhere).
    blocks = "\n".join(f"[{chunk.handle}] {_delimit(chunk.text)}" for chunk in chunks)
    return f"Resume excerpts most relevant to the question:\n{blocks}"


async def _load_resume(session: AsyncSession) -> Document | None:
    result = await session.execute(
        select(Document)
        .where(Document.kind == "resume")
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _load_job(session: AsyncSession, job_doc_id: UUID) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == job_doc_id, Document.kind == "job")
    )
    return result.scalars().first()


async def _load_ready_analysis(
    session: AsyncSession, *, resume_doc_id: UUID, job_doc_id: UUID
) -> tuple[FitAnalysis | None, list[tuple[RequirementMatch, Requirement]]]:
    analysis = (
        (
            await session.execute(
                select(FitAnalysis).where(
                    FitAnalysis.resume_doc_id == resume_doc_id,
                    FitAnalysis.job_doc_id == job_doc_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if analysis is None or analysis.status != "ready":
        return analysis, []

    matches = (
        await session.execute(
            select(RequirementMatch, Requirement)
            .join(Requirement, Requirement.id == RequirementMatch.requirement_id)
            .where(RequirementMatch.fit_analysis_id == analysis.id)
            .order_by(Requirement.ordinal)
        )
    ).all()
    return analysis, [(match, requirement) for match, requirement in matches]


async def _load_all_ready_analyses(
    session: AsyncSession, *, resume_doc_id: UUID
) -> list[tuple[Document, FitAnalysis, list[tuple[RequirementMatch, Requirement]]]]:
    rows = (
        await session.execute(
            select(FitAnalysis, Document)
            .join(Document, Document.id == FitAnalysis.job_doc_id)
            .where(FitAnalysis.resume_doc_id == resume_doc_id, FitAnalysis.status == "ready")
            .order_by(Document.created_at.desc())
        )
    ).all()

    analysis_ids = [analysis.id for analysis, _job in rows]
    matches_by_analysis: dict[UUID, list[tuple[RequirementMatch, Requirement]]] = {}
    if analysis_ids:
        match_rows = (
            await session.execute(
                select(RequirementMatch, Requirement)
                .join(Requirement, Requirement.id == RequirementMatch.requirement_id)
                .where(RequirementMatch.fit_analysis_id.in_(analysis_ids))
                .order_by(Requirement.ordinal)
            )
        ).all()
        for match, requirement in match_rows:
            matches_by_analysis.setdefault(match.fit_analysis_id, []).append(
                (match, requirement)
            )

    return [
        (job, analysis, matches_by_analysis.get(analysis.id, [])) for analysis, job in rows
    ]


async def build_context(
    session: AsyncSession,
    *,
    scope: Literal["job", "all"],
    job_doc_id: UUID | None,
    question: str,
    history: Sequence[Turn],
    embedder: Embedder,
) -> ChatContext:
    """Assemble the prompt context for one chat turn. Read-only, no LLM call.

    Returns the retrieved resume chunks alongside the assembled text (see
    ``ChatContext``) -- Task 18's chat service needs the *same* candidates
    it just put in the prompt to offer as citation handles, not a second,
    independently-retrieved set that only happens to match by coincidence.

    Raises ``ValueError`` if ``scope == "job"`` and ``job_doc_id`` is
    ``None``, or if ``job_doc_id`` does not resolve to a job document.
    """
    if scope == "job" and job_doc_id is None:
        raise ValueError("job_doc_id is required when scope='job'")

    # Runs before any read on `session` -- see the module docstring.
    [question_embedding] = await embedder.embed([question])

    resume = await _load_resume(session)

    sections: list[str] = []

    history_block = _format_history(select_history(history))
    if history_block:
        sections.append(history_block)

    if scope == "job":
        assert job_doc_id is not None  # validated above
        job = await _load_job(session, job_doc_id)
        if job is None:
            raise ValueError(f"job document not found: {job_doc_id}")
        sections.append(_format_job_spec(job))
        if resume is not None:
            analysis, matches = await _load_ready_analysis(
                session, resume_doc_id=resume.id, job_doc_id=job.id
            )
            sections.append(_format_analysis(job, analysis, matches))
    else:
        if resume is not None:
            all_analyses = await _load_all_ready_analyses(session, resume_doc_id=resume.id)
            if all_analyses:
                blocks = [
                    _format_analysis(job, analysis, matches)
                    for job, analysis, matches in all_analyses
                ]
                sections.append(
                    "Cached fit analyses, every job:\n\n" + "\n\n".join(blocks)
                )

    chunks: list[ChunkCandidate] = []
    if resume is not None:
        chunks = await nearest_chunks(
            session, document_id=resume.id, query_embedding=question_embedding
        )
        chunk_block = _format_chunks(chunks)
        if chunk_block:
            sections.append(chunk_block)

    sections.append(f"Question: {question}")

    return ChatContext(
        text="\n\n".join(sections),
        chunks=chunks,
        resume_doc_id=resume.id if resume is not None else None,
    )
