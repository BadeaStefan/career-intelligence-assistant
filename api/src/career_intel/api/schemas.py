"""Request and response models for the HTTP layer.

Kept separate from the ORM models so the wire format is an explicit decision
rather than a side effect of the schema. ``raw_text`` in particular is never
serialised: it is the user's resume.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from career_intel.chat.service import Citation
from career_intel.models import (
    DocumentKind,
    FitAnalysisStatus,
    RequirementImportance,
    RequirementVerdictValue,
)


class PasteRequest(BaseModel):
    kind: DocumentKind
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=512)
    company: str | None = Field(default=None, max_length=512)


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocumentKind
    source: Literal["upload", "paste"]
    title: str | None
    company: str | None
    filename: str | None
    status: Literal["pending", "ready", "failed"]
    extraction_status: Literal["pending", "ready", "failed"]
    created_at: datetime


class AnalysisSummary(BaseModel):
    """One row of the job rail (``GET /analyses``)."""

    job_doc_id: uuid.UUID
    title: str | None
    company: str | None
    status: FitAnalysisStatus
    overall_score: float | None


class EvidenceSummary(BaseModel):
    """A citation backing one requirement match.

    ``char_start``/``char_end`` are null when the extracted quote could not
    be located in the resume's raw text (non-negotiable #6) -- still valid
    evidence, just not highlightable.
    """

    text: str
    char_start: int | None
    char_end: int | None


class RequirementMatchSummary(BaseModel):
    requirement_id: uuid.UUID
    requirement_text: str
    requirement_importance: RequirementImportance
    verdict: RequirementVerdictValue
    rationale: str
    evidence: list[EvidenceSummary]


class AnalysisDetail(BaseModel):
    """The full breakdown for ``GET /analyses/{job_doc_id}``.

    ``matches`` is ordered strong, then partial, then missing -- not split
    into three separate keys, since every match already carries its own
    ``verdict``.
    """

    job_doc_id: uuid.UUID
    status: FitAnalysisStatus
    overall_score: float | None
    matches: list[RequirementMatchSummary]


class CreateSessionRequest(BaseModel):
    job_doc_id: uuid.UUID | None = None


class SessionSummary(BaseModel):
    """``POST /chat/sessions``' response -- just the id the client sends
    ``POST .../messages`` requests to next."""

    id: uuid.UUID


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    scope: Literal["job", "all"]


class MessageSummary(BaseModel):
    """One row of ``GET /chat/sessions/{id}/messages``, carrying the scope
    it was asked/answered under (spec §6: scope lives per message)."""

    role: Literal["user", "assistant"]
    content: str
    scope: Literal["job", "all"]
    citations: list[Citation]


class PrepQuestionDetail(BaseModel):
    """One row of ``GET``/``POST`` ``/prep/{job_doc_id}``'s ``questions`` list.

    ``verdict`` is read off the parent ``FitAnalysis``'s matching
    ``RequirementMatch`` -- what verdict this question is anchored to -- not
    persisted redundantly on ``PrepQuestion`` itself (spec §4's update note,
    same reasoning ``RequirementMatch`` already applies to its own score).
    """

    id: uuid.UUID
    requirement_id: uuid.UUID
    requirement_text: str
    verdict: RequirementVerdictValue
    question: str
    why_they_will_ask: str
    how_to_frame: str
    evidence: list[EvidenceSummary]


class PrepDetail(BaseModel):
    """The full breakdown for ``GET``/``POST`` ``/prep/{job_doc_id}``."""

    job_doc_id: uuid.UUID
    questions: list[PrepQuestionDetail]


class LlmCallTrace(BaseModel):
    """Safe, request-scoped provider telemetry exposed to the trace drawer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str
    purpose: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    cost_usd: float | None
    status: Literal["succeeded", "failed"]
    error_type: str | None
    created_at: datetime


class RetrievalCandidateTrace(BaseModel):
    id: str
    handle: str
    score: float


class RetrievalResultsTrace(BaseModel):
    candidates: list[RetrievalCandidateTrace]


class RetrievalTraceSummary(BaseModel):
    """Retrieval metadata only: identifiers and scores, never query/document text."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str
    results: RetrievalResultsTrace
    created_at: datetime


class TraceDetail(BaseModel):
    llm_calls: list[LlmCallTrace]
    retrievals: list[RetrievalTraceSummary]
