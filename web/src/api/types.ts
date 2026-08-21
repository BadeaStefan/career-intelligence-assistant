export type DocumentKind = "resume" | "job";
export type DocumentSource = "upload" | "paste";
export type ProcessingStatus = "pending" | "ready" | "failed";

/**
 * Mirrors the API's DocumentSummary.
 *
 * Two status fields, deliberately. `status` is settled during the upload
 * request, because parsing happens there -- so a document that appears in a
 * listing at all is already usable. `extraction_status` tracks the background
 * enrichment, and that is what the UI shows as "processing".
 */
export interface DocumentSummary {
  id: string;
  kind: DocumentKind;
  source: DocumentSource;
  title: string | null;
  company: string | null;
  filename: string | null;
  status: ProcessingStatus;
  extraction_status: ProcessingStatus;
  created_at: string;
}

export interface PasteInput {
  kind: DocumentKind;
  text: string;
  title?: string;
  company?: string;
}

export type FitAnalysisStatus = "pending" | "ready" | "failed";
export type RequirementImportance = "required" | "preferred";
export type RequirementVerdict = "strong" | "partial" | "missing";

/** Mirrors the API's AnalysisSummary -- one row of `GET /analyses`. */
export interface AnalysisSummary {
  job_doc_id: string;
  title: string | null;
  company: string | null;
  status: FitAnalysisStatus;
  overall_score: number | null;
}

/**
 * Mirrors the API's EvidenceSummary. `char_start`/`char_end` are null when
 * the extracted quote could not be located in the resume's raw text
 * (CLAUDE.md non-negotiable #6) -- still valid evidence, just not
 * highlightable by offset.
 */
export interface EvidenceSummary {
  text: string;
  char_start: number | null;
  char_end: number | null;
}

/** Mirrors the API's RequirementMatchSummary. */
export interface RequirementMatchSummary {
  requirement_id: string;
  requirement_text: string;
  requirement_importance: RequirementImportance;
  verdict: RequirementVerdict;
  rationale: string;
  evidence: EvidenceSummary[];
}

/**
 * Mirrors the API's AnalysisDetail -- the full breakdown for
 * `GET /analyses/{job_doc_id}`. `matches` arrives already ordered strong,
 * then partial, then missing.
 */
export interface AnalysisDetail {
  job_doc_id: string;
  status: FitAnalysisStatus;
  overall_score: number | null;
  matches: RequirementMatchSummary[];
}

/** Chat scope, chosen by the dock's explicit toggle (spec §6). Travels per
 * message, not per session -- every `POST .../messages` body carries it. */
export type ChatScope = "job" | "all";

/**
 * Mirrors the API's Citation -- a chat citation already resolved to the
 * chunk and span it points at, not the bare "[c1]" handle the model wrote
 * (that handle is only ever meaningful for the one retrieval call that
 * assigned it, per `chat/service.py`'s docstring).
 */
export interface Citation {
  handle: string;
  document_id: string;
  chunk_id: string;
  char_start: number;
  char_end: number;
}

/** Mirrors the API's SessionSummary -- `POST /chat/sessions`' response. */
export interface ChatSessionSummary {
  id: string;
}

/** Mirrors the API's ChatReply -- `POST /chat/sessions/{id}/messages`' response. */
export interface ChatReply {
  content: string;
  citations: Citation[];
}

/**
 * Mirrors the API's MessageSummary -- one row of
 * `GET /chat/sessions/{id}/messages`, carrying the scope it was actually
 * asked/answered under (spec §6: scope lives per message, so history must
 * render from this field, never from whatever the toggle currently shows).
 */
export interface MessageSummary {
  role: "user" | "assistant";
  content: string;
  scope: ChatScope;
  citations: Citation[];
}

/**
 * Mirrors the API's PrepQuestionDetail. `verdict` is read off the parent
 * fit analysis's matching requirement match, not persisted redundantly on
 * the question itself -- what verdict this question is anchored to.
 */
export interface PrepQuestionDetail {
  id: string;
  requirement_id: string;
  requirement_text: string;
  verdict: RequirementVerdict;
  question: string;
  why_they_will_ask: string;
  how_to_frame: string;
  evidence: EvidenceSummary[];
}

/**
 * Mirrors the API's PrepDetail -- the full breakdown for
 * `GET`/`POST /prep/{job_doc_id}`.
 */
export interface PrepDetail {
  job_doc_id: string;
  questions: PrepQuestionDetail[];
}
