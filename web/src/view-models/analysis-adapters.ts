/**
 * Pure functions mapping the API's wire-format analysis shapes
 * (`AnalysisSummary`, `AnalysisDetail`, plus `DocumentSummary` for
 * title/company/extraction_status context) into the presentation layer's
 * `JobRailItem` / `AnalysisView`. Kept separate from `hooks/useAnalysis.ts`
 * so these are independently unit-testable against fixtures, with no
 * TanStack Query or fetch involved.
 */
import type { AnalysisDetail, AnalysisSummary, DocumentSummary, RequirementMatchSummary } from "../api/types";
import type { AnalysisView, JobHeadingView, JobRailItem, RequirementView, VerdictCounts } from "./dashboard";

export function headingFor(document: DocumentSummary): JobHeadingView {
  return {
    id: document.id,
    title: document.title ?? document.filename ?? "Untitled role",
    company: document.company ?? "Company not specified",
  };
}

/**
 * `GET /analyses` (the list) has no per-job verdict breakdown by design, so
 * a "ready" row's `verdictCounts` always defaults to zero here -- callers
 * that have the full `AnalysisDetail` for the *selected* job (via
 * `useAnalysisDetail`) should layer the real counts on afterwards with
 * `withSelectedVerdictCounts`, never by fetching every job's detail.
 */
export function toJobRailItem(document: DocumentSummary, summary: AnalysisSummary | undefined): JobRailItem {
  const base = headingFor(document);

  if (document.status === "failed" || document.extraction_status === "failed") {
    return { ...base, state: "failed" };
  }
  if (document.extraction_status === "pending") {
    return { ...base, state: "analysing" };
  }

  // extraction_status === "ready" from here: the job itself is usable, so
  // whatever comes next is the fit-analysis side of the story.
  if (!summary) {
    // No fit_analyses row at all yet -- schedule_fit_analyses hasn't
    // claimed this job/resume pair (mirrors the 404 case the detail
    // endpoint returns for the same underlying situation; see ruling 3 in
    // the continuation brief). Not a service outage, so "analysing", not
    // "unavailable".
    return { ...base, state: "analysing" };
  }
  if (summary.status === "pending") return { ...base, state: "analysing" };
  if (summary.status === "failed") return { ...base, state: "failed", reason: "analysis" };

  return { ...base, state: "ready", score: summary.overall_score ?? 0, verdictCounts: zeroCounts() };
}

/** Ruling 2: merge real verdict counts into the selected job's rail row. */
export function withSelectedVerdictCounts(item: JobRailItem, detail: AnalysisDetail | null | undefined): JobRailItem {
  if (item.state !== "ready" || !detail || detail.status !== "ready") return item;
  return { ...item, verdictCounts: verdictCountsFromMatches(detail.matches) };
}

export function verdictCountsFromMatches(matches: RequirementMatchSummary[]): VerdictCounts {
  const counts = zeroCounts();
  for (const match of matches) counts[match.verdict] += 1;
  return counts;
}

function zeroCounts(): VerdictCounts {
  return { strong: 0, partial: 0, missing: 0 };
}

/**
 * `detail === null` is a confirmed 404 (no fit_analyses row exists yet).
 * `detail === undefined` means "not resolved" -- still loading, or the
 * analyses API errored; callers decide whether to call this at all in that
 * case (see App.tsx's judgment call in the continuation report) but if they
 * do, "unavailable" is the safe fallback here too.
 */
export function toAnalysisView(
  document: DocumentSummary,
  detail: AnalysisDetail | null | undefined,
  onRetry?: () => void,
): AnalysisView {
  const job = headingFor(document);

  if (document.status === "failed" || document.extraction_status === "failed") {
    return { status: "extraction-failed", job };
  }
  if (document.extraction_status === "pending") {
    return { status: "analysing", job };
  }

  if (detail === null) {
    // Ruling 3: extraction succeeded but no fit_analyses row exists yet --
    // the resume hasn't finished indexing, so nothing has claimed this
    // job. Same copy as "analysing", not a new variant.
    return { status: "analysing", job };
  }
  if (detail === undefined) {
    return { status: "unavailable", job };
  }

  if (detail.status === "pending") return { status: "analysing", job };
  if (detail.status === "failed") return { status: "analysis-failed", job, onRetry };

  return {
    status: "ready",
    job,
    score: detail.overall_score ?? 0,
    requirements: detail.matches.map(toRequirementView),
    // Interview prep (Task 20) is Phase 4 and not built yet -- PrepPane
    // already renders a graceful empty state for this (ruling 5).
    prepQuestions: [],
  };
}

function toRequirementView(match: RequirementMatchSummary): RequirementView {
  const [firstEvidence] = match.evidence;

  return {
    id: match.requirement_id,
    text: match.requirement_text,
    importance: match.requirement_importance,
    verdict: match.verdict,
    rationale: match.rationale,
    // No per-match retrieval score is persisted by the real pipeline
    // (ruling 1) -- left undefined, never fabricated.
    evidence: firstEvidence
      ? { location: locationLabel(firstEvidence.char_start, firstEvidence.char_end), quote: firstEvidence.text }
      : undefined,
    // RequirementView carries a single citation; when a match has more than
    // one, the trailing clause names the count instead of silently dropping
    // the rest.
    gap: match.evidence.length > 1 ? `${match.evidence.length} spans cited` : undefined,
  };
}

function locationLabel(charStart: number | null, charEnd: number | null): string {
  // The wire format carries only character offsets, no page/section
  // metadata (CLAUDE.md non-negotiable #6: offsets are located, never
  // guessed, and are null when the quote couldn't be found verbatim).
  return charStart !== null && charEnd !== null
    ? `chars ${charStart}–${charEnd}`
    : "location not found in resume text";
}
