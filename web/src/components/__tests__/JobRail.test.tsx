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
        resume={{ id: "resume-1", filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="nova"
        onSelect={onSelect}
        onAddJob={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByText("Analysing · judging 5/12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^backend engineer at nova fintech$/i })).toHaveAttribute(
      "aria-current",
      "true",
    );

    await userEvent.click(screen.getByRole("button", { name: /^platform engineer at snyk$/i }));
    expect(onSelect).toHaveBeenCalledWith("snyk");
  });

  it("labels extraction failures without inventing a score", () => {
    render(
      <JobRail
        resume={{ id: "resume-1", filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="snyk"
        onSelect={() => undefined}
        onAddJob={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("Extraction error · 09:21")).toBeInTheDocument();
  });

  it("labels a failed fit analysis distinctly from an extraction failure", () => {
    const analysisFailedJobs: JobRailItem[] = [
      { id: "nova", title: "Backend Engineer", company: "Nova Fintech", state: "failed", failedAt: "10:04", reason: "analysis" },
    ];
    render(
      <JobRail
        resume={{ id: "resume-1", filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={analysisFailedJobs}
        selectedJobId="nova"
        onSelect={() => undefined}
        onAddJob={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByText("Analysis error · 10:04")).toBeInTheDocument();
    expect(screen.queryByText(/extraction error/i)).not.toBeInTheDocument();
  });

  it("deletes the resume or a job without selecting the job underneath", async () => {
    const onDelete = vi.fn();
    const onSelect = vi.fn();
    render(
      <JobRail
        resume={{ id: "resume-1", filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="nova"
        onSelect={onSelect}
        onAddJob={() => undefined}
        onDelete={onDelete}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Delete resume alex-moraru-resume.pdf" }));
    expect(onDelete).toHaveBeenCalledWith("resume-1");

    await userEvent.click(screen.getByRole("button", { name: "Delete job Backend Engineer at Nova Fintech" }));
    expect(onDelete).toHaveBeenLastCalledWith("nova");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("offers the add action as the rail's footer without a separate hint line", () => {
    render(
      <JobRail
        resume={{ id: "resume-1", filename: "alex-moraru-resume.pdf", detail: "2 pages · 118 spans indexed" }}
        jobs={jobs}
        selectedJobId="nova"
        onSelect={() => undefined}
        onAddJob={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "+ Add job" })).toBeEnabled();
    expect(screen.queryByText(/upload a file or paste text/i)).not.toBeInTheDocument();
  });
});
