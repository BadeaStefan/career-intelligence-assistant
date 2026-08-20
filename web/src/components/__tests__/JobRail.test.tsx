import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JobRail } from "../JobRail";
import type { JobRailItem } from "../../view-models/dashboard";

const jobs: JobRailItem[] = [
  {
    id: "nova",
    title: "Backend Engineer",
    company: "Nova Fintech",
    state: "ready",
    score: 0.84,
    verdictCounts: { strong: 10, partial: 1, missing: 1 },
  },
  {
    id: "datadog",
    title: "Senior Backend Engineer",
    company: "Datadog",
    state: "analysing",
    progress: { complete: 5, total: 12, secondsRemaining: 8 },
  },
  {
    id: "snyk",
    title: "Platform Engineer",
    company: "Snyk",
    state: "failed",
    failedAt: "09:21",
  },
];

describe("JobRail", () => {
  it("selects jobs and exposes analysis progress in requirements", async () => {
    const onSelect = vi.fn();
    render(
      <JobRail
        resume={{ filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="nova"
        onSelect={onSelect}
        onAddJob={() => undefined}
      />,
    );

    expect(screen.getByText("Analysing · judging 5/12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /backend engineer at nova fintech/i })).toHaveAttribute(
      "aria-current",
      "true",
    );

    await userEvent.click(screen.getByRole("button", { name: /platform engineer at snyk/i }));
    expect(onSelect).toHaveBeenCalledWith("snyk");
  });

  it("labels extraction failures without inventing a score", () => {
    render(
      <JobRail
        resume={{ filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="snyk"
        onSelect={() => undefined}
        onAddJob={() => undefined}
      />,
    );

    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("Extraction error · 09:21")).toBeInTheDocument();
  });
});
