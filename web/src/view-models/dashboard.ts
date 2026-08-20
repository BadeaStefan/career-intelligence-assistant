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
  | { state: "failed"; failedAt?: string }
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
  retrievalScore: number;
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
  | { status: "unavailable"; job: JobHeadingView };
