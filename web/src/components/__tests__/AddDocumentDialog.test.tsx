import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { AddDocumentDialog, rejectReason } from "../AddDocumentDialog";

// jsdom implements <dialog> as an inert element: showModal/close are absent,
// so the component's open effect would throw. Stubbing them here keeps the
// test exercising the real component rather than a testing-only branch.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
  };
});

const noop = () => undefined;

function renderDialog(overrides: Partial<Parameters<typeof AddDocumentDialog>[0]> = {}) {
  const props = {
    kind: "job" as const,
    onClose: noop,
    onSubmitFile: noop,
    onSubmitText: noop,
    ...overrides,
  };
  render(<AddDocumentDialog {...props} />);
  return props;
}

describe("AddDocumentDialog", () => {
  it("sends pasted text along with the title and company the user typed", async () => {
    const onSubmitText = vi.fn();
    renderDialog({ onSubmitText });

    await userEvent.type(screen.getByLabelText(/title/i), "Senior Backend Engineer");
    await userEvent.type(screen.getByLabelText(/company/i), "Datadog");
    await userEvent.type(screen.getByLabelText(/posting text/i), "5+ years Python");
    await userEvent.click(screen.getByRole("button", { name: /add job/i }));

    expect(onSubmitText).toHaveBeenCalledWith({
      text: "5+ years Python",
      title: "Senior Backend Engineer",
      company: "Datadog",
    });
  });

  // The whole point of the change: a job posting can arrive as a file, which
  // the shipped UI only ever offered for resumes.
  it("accepts a dropped PDF job posting", () => {
    const onSubmitFile = vi.fn();
    renderDialog({ onSubmitFile });
    const file = new File(["posting"], "job.pdf", { type: "application/pdf" });

    fireEvent.drop(screen.getByTestId("add-dropzone"), { dataTransfer: { files: [file] } });

    expect(onSubmitFile).toHaveBeenCalledWith(file);
  });

  it("refuses a file over the limit without spending a request on it", () => {
    const onSubmitFile = vi.fn();
    renderDialog({ onSubmitFile, maxUploadBytes: 1024 });
    const file = new File(["x".repeat(2048)], "big.pdf", { type: "application/pdf" });

    fireEvent.drop(screen.getByTestId("add-dropzone"), { dataTransfer: { files: [file] } });

    expect(onSubmitFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/1 KB/);
  });

  it("refuses a type the parser cannot read", () => {
    const onSubmitFile = vi.fn();
    renderDialog({ onSubmitFile });
    const file = new File(["binary"], "screenshot.png", { type: "image/png" });

    fireEvent.drop(screen.getByTestId("add-dropzone"), { dataTransfer: { files: [file] } });

    expect(onSubmitFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/PDF, DOCX/i);
  });

  it("keeps the submit button disabled until there is something to send", async () => {
    renderDialog();
    const submit = screen.getByRole("button", { name: /add job/i });

    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/posting text/i), "text");
    expect(submit).toBeEnabled();
  });

  // A server rejection used to close the native prompt and take the typed
  // text with it. The dialog stays put so the user can fix and retry.
  it("shows a server rejection inline without discarding what was typed", async () => {
    renderDialog({ serverError: "Upload exceeds the maximum of 1024 bytes." });

    await userEvent.type(screen.getByLabelText(/posting text/i), "keep me");

    expect(screen.getByRole("alert")).toHaveTextContent(/exceeds the maximum/i);
    expect(screen.getByLabelText(/posting text/i)).toHaveValue("keep me");
  });

  // Same contract as WorkspaceEmptyState: the limit belongs to the server,
  // and a confident stale literal is the failure this avoids.
  it("omits the upload limit rather than inventing one before config arrives", () => {
    renderDialog();

    expect(screen.queryByText(/max .* MB/i)).not.toBeInTheDocument();
  });

  it("drops the job-only metadata fields when adding a resume", () => {
    renderDialog({ kind: "resume" });

    expect(screen.queryByLabelText(/company/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/resume text/i)).toBeInTheDocument();
  });

  it("renders nothing at all when no kind is being added", () => {
    renderDialog({ kind: null });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("rejectReason", () => {
  // The server dispatches on content type and treats an unknown one as
  // application/octet-stream, which it accepts. Browsers report "" for plenty
  // of ordinary files, so rejecting an empty type would refuse valid uploads.
  it("accepts a file whose type the browser could not determine", () => {
    expect(rejectReason(new File(["cv"], "cv.docx", { type: "" }))).toBeNull();
  });

  it("accepts every type the parser supports", () => {
    const types = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
      "text/markdown",
      "application/octet-stream",
    ];

    for (const type of types) {
      expect(rejectReason(new File(["x"], "f", { type }))).toBeNull();
    }
  });

  it("has nothing to say about size while the limit is unknown", () => {
    expect(rejectReason(new File(["x".repeat(50)], "f.pdf", { type: "application/pdf" }))).toBeNull();
  });
});
