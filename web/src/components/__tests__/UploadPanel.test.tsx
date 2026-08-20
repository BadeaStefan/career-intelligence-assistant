import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DocumentSummary } from "../../api/types";
import { UploadPanel } from "../UploadPanel";

function makeDocument(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: "1",
    kind: "resume",
    source: "upload",
    title: "cv.pdf",
    company: null,
    filename: "cv.pdf",
    status: "ready",
    extraction_status: "ready",
    created_at: "2026-08-20T12:00:00Z",
    ...overrides,
  };
}

describe("UploadPanel", () => {
  it("shows a document with pending extraction as processing", () => {
    render(<UploadPanel documents={[makeDocument({ extraction_status: "pending" })]} />);

    expect(screen.getByText(/processing/i)).toBeInTheDocument();
  });

  it("shows a fully enriched document as ready", () => {
    render(<UploadPanel documents={[makeDocument()]} />);

    expect(screen.getByText(/^ready$/i)).toBeInTheDocument();
  });

  it("reports a failed analysis without implying the document is unusable", () => {
    // status stays ready: parsing succeeded, so the text is stored and the
    // document is still answerable. Only enrichment failed.
    render(
      <UploadPanel
        documents={[makeDocument({ status: "ready", extraction_status: "failed" })]}
      />,
    );

    expect(screen.getByText(/analysis failed/i)).toBeInTheDocument();
  });

  it("invites a first upload when there is nothing yet", () => {
    render(<UploadPanel documents={[]} />);

    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument();
  });

  it("separates the resume from job postings", () => {
    render(
      <UploadPanel
        documents={[
          makeDocument({ id: "1", kind: "resume", title: "cv.pdf" }),
          makeDocument({ id: "2", kind: "job", title: "Datadog - Senior Backend" }),
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: /resume/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /job postings/i })).toBeInTheDocument();
    expect(screen.getByText("Datadog - Senior Backend")).toBeInTheDocument();
  });
});
