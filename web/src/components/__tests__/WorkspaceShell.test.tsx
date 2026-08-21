import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatDock } from "../ChatDock";
import { TraceDrawer } from "../TraceDrawer";
import { WorkspaceEmptyState } from "../WorkspaceEmptyState";

describe("workspace supporting surfaces", () => {
  it("keeps the empty state focused on indexing a resume", () => {
    render(<WorkspaceEmptyState onChooseFile={() => undefined} onFile={() => undefined} onPaste={() => undefined} maxUploadBytes={20 * 1024 * 1024} />);

    expect(screen.getByRole("heading", { name: "Start with the resume" })).toBeInTheDocument();
    expect(screen.getByText(/nothing can run until one is indexed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /choose a file/i })).toBeInTheDocument();
    expect(screen.getByText(/max 20 MB/i)).toBeInTheDocument();
  });

  // The limit is the server's to state. Until /config answers, the component
  // has no honest value to show -- and a stale literal shown confidently is
  // the exact failure this prop exists to remove.
  it("omits the upload limit rather than inventing one before config arrives", () => {
    render(<WorkspaceEmptyState onChooseFile={() => undefined} onFile={() => undefined} onPaste={() => undefined} />);

    expect(screen.getByRole("heading", { name: "Start with the resume" })).toBeInTheDocument();
    expect(screen.queryByText(/max .* MB/i)).not.toBeInTheDocument();
  });

  it("accepts a dropped resume file", () => {
    const onFile = vi.fn();
    render(<WorkspaceEmptyState onChooseFile={() => undefined} onFile={onFile} onPaste={() => undefined} />);
    const file = new File(["resume"], "cv.txt", { type: "text/plain" });

    fireEvent.drop(screen.getByTestId("resume-dropzone"), { dataTransfer: { files: [file] } });

    expect(onFile).toHaveBeenCalledWith(file);
  });

  it("changes chat scope while leaving the unfinished composer disabled", async () => {
    render(<ChatDock jobCompany="Datadog" jobCount={3} requirementCount={36} connected={false} />);

    await userEvent.click(screen.getByRole("button", { name: "All jobs" }));
    expect(screen.getByText(/scoped to 3 jobs/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByText(/available when the chat service is connected/i)).toBeInTheDocument();
  });

  it("forces failed jobs out of single-job chat scope", () => {
    render(<ChatDock jobCompany="Snyk" jobCount={2} requirementCount={24} connected={false} forceAllJobs excludedJob="Snyk" />);

    expect(screen.getByRole("button", { name: "This job" })).toBeDisabled();
    expect(screen.getByText(/snyk excluded/i)).toBeInTheDocument();
  });

  it("opens trace details and reports backend availability honestly", async () => {
    render(<TraceDrawer open onOpenChange={() => undefined} />);

    expect(screen.getByText(/send a chat message to inspect its trace details/i)).toBeInTheDocument();
  });
});
