import { describe, expect, it } from "vitest";

import type {
  AnalysisDetail,
  AnalysisSummary,
  DocumentSummary,
  PrepDetail,
  PrepQuestionDetail,
  RequirementMatchSummary,
} from "../../api/types";
import {
  headingFor,
  toAnalysisView,
  toJobRailItem,
  verdictCountsFromMatches,
  withSelectedVerdictCounts,
} from "../analysis-adapters";

function document(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: "job-1",
    kind: "job",
    source: "paste",
    title: "Senior Backend Engineer",
    company: "Datadog",
    filename: null,
    status: "ready",
    extraction_status: "ready",
    created_at: "2026-08-20T09:00:00Z",
    ...overrides,
  };
}

function match(overrides: Partial<RequirementMatchSummary> = {}): RequirementMatchSummary {
  return {
    requirement_id: "req-1",
    requirement_text: "Python, 5+ years production experience",
    requirement_importance: "required",
    verdict: "strong",
    rationale: "Six years of continuous Python across three roles.",
    evidence: [{ text: "Built ingestion pipeline in Python", char_start: 120, char_end: 156 }],
    ...overrides,
  };
}

function prepQuestion(overrides: Partial<PrepQuestionDetail> = {}): PrepQuestionDetail {
  return {
    id: "q-1",
    requirement_id: "req-2",
    requirement_text: "Kubernetes in production",
    verdict: "missing",
    question: "How would you take ownership of a service already deployed on Kubernetes?",
    why_they_will_ask: "They will test whether you can name what you do not know.",
    how_to_frame: "Acknowledge the gap, then transfer from on-call ownership.",
    evidence: [],
    ...overrides,
  };
}

describe("toAnalysisView", () => {
  it("maps a ready analysis with matches into the ready AnalysisView, leaving retrievalScore unset", () => {
    const detail: AnalysisDetail = {
      job_doc_id: "job-1",
      status: "ready",
      overall_score: 0.72,
      matches: [
        match({ requirement_id: "req-1", verdict: "strong" }),
        match({
          requirement_id: "req-2",
          requirement_text: "Kubernetes in production",
          verdict: "missing",
          rationale: "No production Kubernetes evidence anywhere in the document.",
          evidence: [],
        }),
        match({
          requirement_id: "req-3",
          requirement_text: "Distributed tracing",
          verdict: "partial",
          evidence: [
            { text: "Instrumented traces with OpenTelemetry", char_start: 40, char_end: 78 },
            { text: "Set up Jaeger for one service", char_start: null, char_end: null },
          ],
        }),
      ],
    };

    const view = toAnalysisView(document(), detail);

    expect(view.status).toBe("ready");
    if (view.status !== "ready") throw new Error("expected ready");
    expect(view.score).toBe(0.72);
    expect(view.prepQuestions).toEqual([]);
    expect(view.requirements).toHaveLength(3);

    const strong = view.requirements[0]!;
    expect(strong.retrievalScore).toBeUndefined();
    expect(strong.evidence).toEqual({ location: "chars 120–156", quote: "Built ingestion pipeline in Python" });

    const missing = view.requirements[1]!;
    expect(missing.evidence).toBeUndefined();
    expect(missing.nearestMiss).toBeUndefined();

    const partial = view.requirements[2]!;
    expect(partial.evidence?.location).toBe("chars 40–78");
    expect(partial.gap).toBe("2 spans cited");
  });

  it("labels evidence with an unlocatable quote instead of guessing a location", () => {
    const detail: AnalysisDetail = {
      job_doc_id: "job-1",
      status: "ready",
      overall_score: 0.5,
      matches: [
        match({ evidence: [{ text: "some resume text", char_start: null, char_end: null }] }),
      ],
    };

    const view = toAnalysisView(document(), detail);
    if (view.status !== "ready") throw new Error("expected ready");
    expect(view.requirements[0]!.evidence?.location).toBe("location not found in resume text");
  });

  it("maps a pending fit analysis to the analysing view", () => {
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "pending", overall_score: null, matches: [] };
    expect(toAnalysisView(document(), detail)).toEqual({ status: "analysing", job: headingFor(document()) });
  });

  it("maps a 404 (no fit_analyses row yet) while extraction is ready to analysing, not unavailable", () => {
    expect(toAnalysisView(document(), null)).toEqual({ status: "analysing", job: headingFor(document()) });
  });

  it("maps a failed fit analysis to analysis-failed with a working retry callback, distinct from extraction-failed", () => {
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "failed", overall_score: null, matches: [] };
    const onRetry = () => undefined;

    const view = toAnalysisView(document(), detail, onRetry);

    expect(view).toEqual({ status: "analysis-failed", job: headingFor(document()), onRetry });
    expect(view.status).not.toBe("extraction-failed");
  });

  it("keeps document-level extraction failure as extraction-failed regardless of any fit analysis detail", () => {
    const failedDoc = document({ extraction_status: "failed" });
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "ready", overall_score: 0.9, matches: [] };

    expect(toAnalysisView(failedDoc, detail).status).toBe("extraction-failed");
  });

  it("shows analysing while extraction itself is still pending", () => {
    expect(toAnalysisView(document({ extraction_status: "pending" }), undefined).status).toBe("analysing");
  });

  it("falls back to unavailable when detail is unresolved (still loading / errored)", () => {
    expect(toAnalysisView(document(), undefined).status).toBe("unavailable");
  });

  it("maps prep questions into PrepQuestionView, ordinal padded and 1-indexed", () => {
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "ready", overall_score: 0.72, matches: [] };
    const prep: PrepDetail = {
      job_doc_id: "job-1",
      questions: [
        prepQuestion({ id: "q-1" }),
        prepQuestion({
          id: "q-2",
          requirement_id: "req-3",
          requirement_text: "Distributed tracing",
          verdict: "partial",
          question: "Walk me through a time you diagnosed a latency regression.",
          evidence: [{ text: "Instrumented traces with OpenTelemetry", char_start: 40, char_end: 78 }],
        }),
      ],
    };

    const view = toAnalysisView(document(), detail, undefined, prep);

    expect(view.status).toBe("ready");
    if (view.status !== "ready") throw new Error("expected ready");
    expect(view.prepQuestions).toEqual([
      {
        id: "q-1",
        ordinal: "01",
        question: "How would you take ownership of a service already deployed on Kubernetes?",
        requirement: "Kubernetes in production",
        verdict: "missing",
        why: "They will test whether you can name what you do not know.",
        framing: "Acknowledge the gap, then transfer from on-call ownership.",
        evidence: undefined,
      },
      {
        id: "q-2",
        ordinal: "02",
        question: "Walk me through a time you diagnosed a latency regression.",
        requirement: "Distributed tracing",
        verdict: "partial",
        why: "They will test whether you can name what you do not know.",
        framing: "Acknowledge the gap, then transfer from on-call ownership.",
        evidence: { location: "chars 40–78", quote: "Instrumented traces with OpenTelemetry" },
      },
    ]);
  });

  it("labels a prep question's unlocatable evidence the same way a requirement's is labelled", () => {
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "ready", overall_score: 0.5, matches: [] };
    const prep: PrepDetail = {
      job_doc_id: "job-1",
      questions: [
        prepQuestion({ evidence: [{ text: "some resume text", char_start: null, char_end: null }] }),
      ],
    };

    const view = toAnalysisView(document(), detail, undefined, prep);
    if (view.status !== "ready") throw new Error("expected ready");
    expect(view.prepQuestions[0]!.evidence?.location).toBe("location not found in resume text");
  });

  it("leaves prepQuestions empty when prep is null (no generated prep yet) or undefined (not loaded)", () => {
    const detail: AnalysisDetail = { job_doc_id: "job-1", status: "ready", overall_score: 0.5, matches: [] };

    const withNull = toAnalysisView(document(), detail, undefined, null);
    const withUndefined = toAnalysisView(document(), detail);
    if (withNull.status !== "ready" || withUndefined.status !== "ready") throw new Error("expected ready");
    expect(withNull.prepQuestions).toEqual([]);
    expect(withUndefined.prepQuestions).toEqual([]);
  });
});

describe("toJobRailItem", () => {
  it("marks a ready job with its score, defaulting verdictCounts to zero (list has no per-job breakdown)", () => {
    const summary: AnalysisSummary = { job_doc_id: "job-1", title: "x", company: "y", status: "ready", overall_score: 0.84 };
    const item = toJobRailItem(document(), summary);

    expect(item).toEqual({
      id: "job-1",
      title: "Senior Backend Engineer",
      company: "Datadog",
      state: "ready",
      score: 0.84,
      verdictCounts: { strong: 0, partial: 0, missing: 0 },
    });
  });

  it("treats an absent fit_analyses row (no summary) for a ready job as analysing, not unavailable", () => {
    expect(toJobRailItem(document(), undefined)).toEqual({
      id: "job-1",
      title: "Senior Backend Engineer",
      company: "Datadog",
      state: "analysing",
    });
  });

  it("labels a failed fit analysis with reason 'analysis', distinct from an extraction failure", () => {
    const summary: AnalysisSummary = { job_doc_id: "job-1", title: "x", company: "y", status: "failed", overall_score: null };
    const item = toJobRailItem(document(), summary);

    expect(item).toEqual({ id: "job-1", title: "Senior Backend Engineer", company: "Datadog", state: "failed", reason: "analysis" });
  });

  it("defaults reason to unset for a document-level extraction failure", () => {
    const item = toJobRailItem(document({ extraction_status: "failed" }), undefined);
    expect(item.state).toBe("failed");
    expect((item as { reason?: string }).reason).toBeUndefined();
  });
});

describe("withSelectedVerdictCounts", () => {
  it("merges real verdict counts from the selected job's detail into its ready rail row", () => {
    const item = toJobRailItem(document(), {
      job_doc_id: "job-1",
      title: "x",
      company: "y",
      status: "ready",
      overall_score: 0.7,
    });
    const detail: AnalysisDetail = {
      job_doc_id: "job-1",
      status: "ready",
      overall_score: 0.7,
      matches: [match({ verdict: "strong" }), match({ verdict: "strong" }), match({ verdict: "missing" })],
    };

    expect(withSelectedVerdictCounts(item, detail)).toEqual({
      ...item,
      verdictCounts: { strong: 2, partial: 0, missing: 1 },
    });
  });

  it("leaves a non-ready row untouched", () => {
    const item = toJobRailItem(document({ extraction_status: "pending" }), undefined);
    expect(withSelectedVerdictCounts(item, null)).toBe(item);
  });

  it("leaves a ready row untouched when detail is not itself ready", () => {
    const item = toJobRailItem(document(), { job_doc_id: "job-1", title: "x", company: "y", status: "ready", overall_score: 0.7 });
    expect(withSelectedVerdictCounts(item, undefined)).toBe(item);
    expect(withSelectedVerdictCounts(item, null)).toBe(item);
  });
});

describe("verdictCountsFromMatches", () => {
  it("counts each verdict independently", () => {
    const counts = verdictCountsFromMatches([
      match({ verdict: "strong" }),
      match({ verdict: "partial" }),
      match({ verdict: "partial" }),
      match({ verdict: "missing" }),
    ]);
    expect(counts).toEqual({ strong: 1, partial: 2, missing: 1 });
  });
});
