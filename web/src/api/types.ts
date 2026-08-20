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
