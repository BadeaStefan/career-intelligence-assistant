import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// Only the network boundary is faked, matching the hook tests: the real
// App, the real hooks and real TanStack Query all run.
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    apiClient: {
      getConfig: vi.fn(),
      listDocuments: vi.fn(),
      uploadDocument: vi.fn(),
      pasteDocument: vi.fn(),
      listAnalyses: vi.fn(),
      getAnalysis: vi.fn(),
      retryAnalysis: vi.fn(),
      createChatSession: vi.fn(),
      listChatMessages: vi.fn(),
      getPrep: vi.fn(),
    },
  };
});

import { ApiError, apiClient } from "../api/client";
import type { DocumentSummary } from "../api/types";
import { App } from "../App";

// jsdom leaves <dialog> inert: showModal/close do not exist, so the
// component's open effect would throw.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
  };
});

const resume: DocumentSummary = {
  id: "resume-1",
  kind: "resume",
  source: "upload",
  title: null,
  company: null,
  filename: "cv.pdf",
  status: "ready",
  extraction_status: "ready",
  created_at: "2026-08-21T10:00:00Z",
};

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  render(<App />, { wrapper: Wrapper });
}

const addedJob: DocumentSummary = { ...resume, id: "job-1", kind: "job", source: "paste", filename: null };

beforeEach(() => {
  vi.mocked(apiClient.getConfig).mockResolvedValue({ max_upload_bytes: 5 * 1024 * 1024 });
  vi.mocked(apiClient.listDocuments).mockResolvedValue([resume]);
  vi.mocked(apiClient.listAnalyses).mockResolvedValue([]);
  vi.mocked(apiClient.createChatSession).mockResolvedValue({ id: "session-1" });
  vi.mocked(apiClient.listChatMessages).mockResolvedValue([]);
  vi.mocked(apiClient.pasteDocument).mockResolvedValue(addedJob);
  vi.mocked(apiClient.uploadDocument).mockResolvedValue(addedJob);
});

describe("adding a job", () => {
  // The regression this change exists to prevent. A native prompt cannot show
  // the limit, cannot report an error without discarding the typed text, and
  // has nowhere to attach a file -- so it must not come back.
  it("opens the dialog rather than a native prompt", async () => {
    const prompt = vi.fn();
    vi.stubGlobal("prompt", prompt);
    renderApp();

    await userEvent.click(await screen.findByRole("button", { name: "+ Add job" }));

    expect(await screen.findByRole("heading", { name: /add job posting/i })).toBeInTheDocument();
    expect(prompt).not.toHaveBeenCalled();
  });

  it("uploads a job posting file, which the shipped UI could not do at all", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "+ Add job" }));
    const file = new File(["posting"], "job.pdf", { type: "application/pdf" });

    const input = screen.getByTestId("add-dropzone").querySelector("input[type=file]");
    await userEvent.upload(input as HTMLInputElement, file);

    await waitFor(() => expect(apiClient.uploadDocument).toHaveBeenCalledWith(file, "job"));
  });

  it("carries the typed title and company through to the paste request", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "+ Add job" }));

    await userEvent.type(screen.getByLabelText(/title/i), "Senior Backend Engineer");
    await userEvent.type(screen.getByLabelText(/company/i), "Datadog");
    await userEvent.type(screen.getByLabelText(/posting text/i), "5+ years Python");
    await userEvent.click(screen.getByRole("button", { name: /^add job$/i }));

    await waitFor(() =>
      expect(apiClient.pasteDocument).toHaveBeenCalledWith({
        kind: "job",
        text: "5+ years Python",
        title: "Senior Backend Engineer",
        company: "Datadog",
      }),
    );
  });

  // The prompt closed on failure and took the text with it. The dialog does
  // not, and the message lands where the user is looking.
  it("keeps the dialog open and reports a rejection inside it", async () => {
    vi.mocked(apiClient.pasteDocument).mockRejectedValue(
      new ApiError("Pasted text exceeds the maximum accepted size.", 413),
    );
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "+ Add job" }));

    await userEvent.type(screen.getByLabelText(/posting text/i), "far too much text");
    await userEvent.click(screen.getByRole("button", { name: /^add job$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/exceeds the maximum/i);
    expect(screen.getByLabelText(/posting text/i)).toHaveValue("far too much text");
  });
});
