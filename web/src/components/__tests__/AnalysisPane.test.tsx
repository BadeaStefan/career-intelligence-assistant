import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnalysisPane } from "../AnalysisPane";
import type { AnalysisView } from "../../view-models/dashboard";

const analysis: AnalysisView = {
  status: "ready",
  job: {
    id: "datadog",
    title: "Senior Backend Engineer",
    company: "Datadog",
    location: "Remote (US)",
    posted: "posted 6d ago",
  },
  score: 0.72,
  requirements: [
    {
      id: "python",
      text: "Python, 5+ years production experience",
      importance: "required",
      verdict: "strong",
      rationale: "Six years of continuous Python across three roles.",
      retrievalScore: 0.91,
      evidence: {
        location: "p.1, Ingestion Platform",
        quote: "Built ingestion pipeline processing 2M events/day (Python, PostgreSQL)",
      },
    },
    {
      id: "kubernetes",
      text: "Kubernetes in production",
      importance: "required",
      verdict: "missing",
      rationale: "No production Kubernetes evidence anywhere in the document.",
      retrievalScore: 0.38,
      nearestMiss: 'closest span: "Docker Compose for local parity" (p.1)',
    },
  ],
  prepQuestions: [
    {
      id: "q1",
      ordinal: "01",
      question: "How would you take ownership of a service already deployed on Kubernetes?",
      requirement: "Kubernetes in production",
      verdict: "missing",
      why: "They will test whether you can name what you do not know.",
      framing: "Acknowledge the gap, then transfer from on-call ownership.",
      evidence: {
        location: "p.1, Ingestion Platform",
        quote: "Primary on-call for ingestion tier, 18 months",
      },
    },
  ],
};

describe("AnalysisPane", () => {
  it("expands a requirement to reveal grounded evidence", async () => {
    render(<AnalysisPane analysis={analysis} />);

    expect(screen.queryByText(/built ingestion pipeline processing/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /python, 5\+ years/i }));
    expect(screen.getByText(/built ingestion pipeline processing/i)).toBeInTheDocument();
    expect(screen.getByText(/retrieval score 0.91/i)).toBeInTheDocument();
  });

  it("shows honest absence instead of a broken citation", async () => {
    render(<AnalysisPane analysis={analysis} />);

    await userEvent.click(screen.getByRole("button", { name: /kubernetes in production/i }));
    expect(screen.getByText("No evidence found")).toBeInTheDocument();
    expect(screen.getByText(/docker compose for local parity/i)).toBeInTheDocument();
    // No fabricated retrieval threshold: the backend has no such cutoff, so
    // the citation-empty copy must never assert one.
    expect(screen.queryByText(/threshold/i)).not.toBeInTheDocument();
  });

  it("never invents a retrieval threshold when a requirement has no citation and no retrieval score", async () => {
    const requirementsWithoutScore: AnalysisView = {
      ...analysis,
      requirements: [
        {
          id: "terraform",
          text: "Terraform in production",
          importance: "preferred",
          verdict: "missing",
          rationale: "No infrastructure-as-code evidence in the document.",
          // Real API data never carries a per-match retrieval score --
          // this fixture matches that shape (see view-models/dashboard.ts).
        },
      ],
    };
    render(<AnalysisPane analysis={requirementsWithoutScore} />);

    await userEvent.click(screen.getByRole("button", { name: /terraform in production/i }));
    expect(screen.getByText("No evidence found")).toBeInTheDocument();
    expect(screen.getByText("No resume evidence was cited for this requirement.")).toBeInTheDocument();
    expect(screen.queryByText(/threshold/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/retrieval score/i)).not.toBeInTheDocument();
  });

  it("switches to interview preparation without fetching", async () => {
    render(<AnalysisPane analysis={analysis} />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));
    expect(screen.getByText(/how would you take ownership/i)).toBeInTheDocument();
    expect(screen.getByText(/^anchored to$/i)).toBeInTheDocument();
  });

  it("renders a distinct failed state for the prep tab when generation errored, with a working retry", async () => {
    const onRetryPrep = vi.fn();
    render(<AnalysisPane analysis={analysis} prepGenerationFailed onRetryPrep={onRetryPrep} />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));

    // Distinct from PrepPane's own "not analysed yet" empty-state copy.
    expect(screen.getByRole("heading", { name: /question generation failed/i })).toBeInTheDocument();
    expect(screen.queryByText(/how would you take ownership/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/questions will appear after fit analysis/i)).not.toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: /retry/i });
    expect(retryButton).toBeEnabled();
    await userEvent.click(retryButton);
    expect(onRetryPrep).toHaveBeenCalledTimes(1);
  });

  it("disables the retry-prep button while a prep retry is already in flight", async () => {
    render(<AnalysisPane analysis={analysis} prepGenerationFailed onRetryPrep={vi.fn()} prepRetryPending />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));
    expect(screen.getByRole("button", { name: /retry/i })).toBeDisabled();
  });

  it("says generation is in flight rather than showing not-analysed-yet copy", async () => {
    // POST /prep 409s unless the fit analysis is already ready, so while the
    // request is in flight "questions will appear after fit analysis" is
    // simply false -- the fit analysis is what triggered this call.
    render(<AnalysisPane analysis={{ ...analysis, prepQuestions: [] }} prepGenerating />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));

    expect(screen.getByText(/generating interview questions/i)).toBeInTheDocument();
    expect(screen.queryByText(/questions will appear after fit analysis/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /question generation failed/i })).not.toBeInTheDocument();
  });

  it("prefers the failure state over the generating state when a retry is in flight", async () => {
    // usePrep's retry sets both flags at once (isGenerateError stays true
    // until the retry resolves). A retry must not read as a first attempt.
    render(
      <AnalysisPane
        analysis={{ ...analysis, prepQuestions: [] }}
        prepGenerationFailed
        prepGenerating
        onRetryPrep={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));
    expect(screen.getByRole("heading", { name: /question generation failed/i })).toBeInTheDocument();
  });

  it("renders the normal prep questions when generation has not failed", async () => {
    render(<AnalysisPane analysis={analysis} prepGenerationFailed={false} />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));
    expect(screen.getByText(/how would you take ownership/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /question generation failed/i })).not.toBeInTheDocument();
  });

  it("renders a failed extraction with recovery actions", () => {
    render(
      <AnalysisPane
        analysis={{
          status: "extraction-failed",
          job: { id: "snyk", title: "Platform Engineer", company: "Snyk" },
          detail: "fetch → 403 · 214 bytes returned · attempt 2 of 2",
          sourceUrl: "https://snyk.io/careers/platform-engineer",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: /couldn't read the requirements/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry extraction/i })).toBeDisabled();
    expect(screen.queryByText(/login wall/i)).not.toBeInTheDocument();
  });

  it("renders a failed fit analysis distinctly from an extraction failure, with a working retry", async () => {
    const onRetry = vi.fn();
    render(
      <AnalysisPane
        analysis={{
          status: "analysis-failed",
          job: { id: "snyk", title: "Platform Engineer", company: "Snyk" },
          onRetry,
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: /the fit analysis for this posting failed/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /couldn't read the requirements/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /paste posting text/i })).not.toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: /retry analysis/i });
    expect(retryButton).toBeEnabled();
    await userEvent.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("disables the retry-analysis button while a retry is already in flight", () => {
    const onRetry = vi.fn();
    render(
      <AnalysisPane
        analysis={{
          status: "analysis-failed",
          job: { id: "snyk", title: "Platform Engineer", company: "Snyk" },
          onRetry,
        }}
        retryPending
      />,
    );

    // Guards the narrow 409 race: a second click landing before the row
    // flips out of "failed" must not be able to fire a second retry.
    expect(screen.getByRole("button", { name: /retry analysis/i })).toBeDisabled();
  });

  it("wires a working re-add recovery action for a failed extraction", async () => {
    const onPaste = vi.fn();
    render(
      <AnalysisPane
        analysis={{
          status: "extraction-failed",
          job: { id: "snyk", title: "Platform Engineer", company: "Snyk" },
        }}
        onPastePosting={onPaste}
      />,
    );

    const addButton = screen.getByRole("button", { name: /add the posting another way/i });
    expect(addButton).toBeEnabled();
    await userEvent.click(addButton);
    expect(onPaste).toHaveBeenCalledTimes(1);
  });
});
