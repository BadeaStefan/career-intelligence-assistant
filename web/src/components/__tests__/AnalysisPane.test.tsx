import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

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
  });

  it("switches to interview preparation without fetching", async () => {
    render(<AnalysisPane analysis={analysis} />);

    await userEvent.click(screen.getByRole("tab", { name: "Interview Prep" }));
    expect(screen.getByText(/how would you take ownership/i)).toBeInTheDocument();
    expect(screen.getByText(/^anchored to$/i)).toBeInTheDocument();
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
});
