export type Verdict = "strong" | "partial" | "missing";

export interface ResumeRailItem {
  filename: string;
  detail: string;
}

export interface VerdictCounts {
  strong: number;
  partial: number;
  missing: number;
}

export type JobRailItem = {
  id: string;
  title: string;
  company: string;
} & (
  | { state: "ready"; score: number; verdictCounts: VerdictCounts }
  | {
      state: "analysing";
      progress?: { complete: number; total: number; secondsRemaining?: number };
    }
  // `reason` defaults to "extraction" when absent, so existing fixtures that
  // never set it keep rendering "Extraction error" byte-for-byte. "analysis"
  // is for a job whose own extraction succeeded but whose fit analysis
  // (the LLM scoring step) failed -- a different failure, same shape.
  | { state: "failed"; failedAt?: string; reason?: "extraction" | "analysis" }
  | { state: "unavailable" }
);

export interface EvidenceView {
  location: string;
  quote: string;
}

export interface RequirementView {
  id: string;
  text: string;
  importance: "required" | "preferred";
  verdict: Verdict;
  rationale: string;
  // The real API never persists a per-match retrieval score (Task 12/13
  // deliberately don't) -- fixture-driven tests still set it, but real data
  // always leaves it undefined and RequirementRow omits the segment.
  retrievalScore?: number;
  evidence?: EvidenceView;
  nearestMiss?: string;
  gap?: string;
}

export interface PrepQuestionView {
  id: string;
  ordinal: string;
  question: string;
  requirement: string;
  verdict: Verdict;
  why: string;
  framing: string;
  evidence?: EvidenceView;
}

export interface JobHeadingView {
  id: string;
  title: string;
  company: string;
  location?: string;
  posted?: string;
}

export type AnalysisView =
  | {
      status: "ready";
      job: JobHeadingView;
      score: number;
      requirements: RequirementView[];
      prepQuestions: PrepQuestionView[];
    }
  | { status: "analysing"; job: JobHeadingView; complete?: number; total?: number }
  | {
      status: "extraction-failed";
      job: JobHeadingView;
      detail?: string;
      sourceUrl?: string;
    }
  // Distinct from "extraction-failed": the posting's requirements were
  // extracted fine, but the LLM scoring step itself failed. Carries its own
  // retry callback (rather than a separate AnalysisPane prop) since it's a
  // per-job action keyed to one analysis row, not a workspace-wide one.
  | { status: "analysis-failed"; job: JobHeadingView; onRetry?: () => void }
  | { status: "unavailable"; job: JobHeadingView };
