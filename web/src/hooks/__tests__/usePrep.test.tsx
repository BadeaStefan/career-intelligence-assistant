import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Only the network boundary (`apiClient`) is faked -- matches
// useChat.test.tsx's/useAnalysis.test.tsx's convention.
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    apiClient: {
      getPrep: vi.fn(),
      generatePrep: vi.fn(),
    },
  };
});

import { ApiError, apiClient } from "../../api/client";
import type { PrepDetail } from "../../api/types";
import { usePrep } from "../usePrep";

const mockedGetPrep = vi.mocked(apiClient.getPrep);
const mockedGeneratePrep = vi.mocked(apiClient.generatePrep);

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const prepDetail: PrepDetail = {
  job_doc_id: "job-1",
  questions: [
    {
      id: "q-1",
      requirement_id: "req-1",
      requirement_text: "Kubernetes in production",
      verdict: "missing",
      question: "How would you take ownership of a service already on Kubernetes?",
      why_they_will_ask: "It's a gap.",
      how_to_frame: "Acknowledge, then bridge.",
      evidence: [],
    },
  ],
};

afterEach(() => {
  // resetAllMocks, not clearAllMocks -- see useAnalysis.test.tsx/useChat.test.tsx
  // for why: a queued mockResolvedValueOnce must never leak into the next test.
  vi.resetAllMocks();
});

describe("usePrep", () => {
  it("treats a 404 from getPrep as a confirmed absence (null), not a thrown error", async () => {
    mockedGetPrep.mockRejectedValue(new ApiError("not found", 404));
    // Generation is left pending forever so the effect's auto-trigger
    // doesn't race this assertion -- this test only cares about the GET's
    // own null-sentinel contract.
    mockedGeneratePrep.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => usePrep("job-1", { enabled: true }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.prep).toBeNull());
  });

  it("re-throws a non-404 error rather than treating it as absence", async () => {
    mockedGetPrep.mockRejectedValue(new ApiError("server error", 500));

    const { result } = renderHook(() => usePrep("job-1", { enabled: true }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.prep).toBeUndefined();
  });

  it("does not query at all while disabled", async () => {
    const { result } = renderHook(() => usePrep("job-1", { enabled: false }), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(false);
    expect(mockedGetPrep).not.toHaveBeenCalled();

    // Give any stray microtask a chance to run before asserting silence.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockedGetPrep).not.toHaveBeenCalled();
  });

  it("triggers exactly one POST on first open when the GET resolves to no cached prep", async () => {
    mockedGetPrep.mockRejectedValue(new ApiError("not found", 404));
    mockedGeneratePrep.mockResolvedValue(prepDetail);

    renderHook(() => usePrep("job-1", { enabled: true }), { wrapper: createWrapper() });

    await waitFor(() => expect(mockedGeneratePrep).toHaveBeenCalledTimes(1));
  });

  it("a second open (re-render, or another component instance for the same job) issues no POST", async () => {
    mockedGetPrep.mockRejectedValue(new ApiError("not found", 404));
    mockedGeneratePrep.mockResolvedValue(prepDetail);

    const { rerender } = renderHook(() => usePrep("job-1", { enabled: true }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(mockedGeneratePrep).toHaveBeenCalledTimes(1));

    // Re-rendering (e.g. a parent re-render with the same job selected)
    // must not fire a second POST once generation has already succeeded for
    // this job.
    rerender();
    rerender();

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockedGeneratePrep).toHaveBeenCalledTimes(1);
  });

  it("never generates when a cached prep already exists (GET returns real data, not 404)", async () => {
    mockedGetPrep.mockResolvedValue(prepDetail);

    const { result } = renderHook(() => usePrep("job-1", { enabled: true }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.prep).toEqual(prepDetail));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockedGeneratePrep).not.toHaveBeenCalled();
  });

  it("triggers a fresh generation for a newly selected job that has no cached prep", async () => {
    mockedGetPrep.mockRejectedValue(new ApiError("not found", 404));
    mockedGeneratePrep.mockResolvedValue(prepDetail);

    const { rerender } = renderHook(
      ({ jobDocId }: { jobDocId: string }) => usePrep(jobDocId, { enabled: true }),
      { wrapper: createWrapper(), initialProps: { jobDocId: "job-1" } },
    );

    await waitFor(() => expect(mockedGeneratePrep).toHaveBeenCalledTimes(1));

    rerender({ jobDocId: "job-2" });

    await waitFor(() => expect(mockedGeneratePrep).toHaveBeenCalledTimes(2));
  });
});
