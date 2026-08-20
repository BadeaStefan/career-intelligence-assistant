import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Only the network boundary (`apiClient`) is faked -- everything else
// (TanStack Query, the hooks under test) runs for real, matching how
// `analysis-adapters.test.ts` fakes only the wire-format inputs going into
// pure functions. Real timers are used throughout (not `vi.useFakeTimers`):
// the poll interval is a real, load-bearing 2s constant, and asserting
// through it directly is more trustworthy than reproducing the timer stack
// TanStack Query's internal scheduling depends on under a fake clock.
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    apiClient: {
      listAnalyses: vi.fn(),
      getAnalysis: vi.fn(),
      retryAnalysis: vi.fn(),
    },
  };
});

import { ApiError, apiClient } from "../../api/client";
import type { AnalysisDetail } from "../../api/types";
import { useAnalysisDetail, useAnalysisList } from "../useAnalysis";

const mockedGetAnalysis = vi.mocked(apiClient.getAnalysis);
const mockedListAnalyses = vi.mocked(apiClient.listAnalyses);

const readyDetail: AnalysisDetail = {
  job_doc_id: "job-1",
  status: "ready",
  overall_score: 0.8,
  matches: [],
};

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// Wrapped in `act` because time genuinely elapsing here can let a scheduled
// refetch resolve and update the query's state outside of any RTL helper
// that would otherwise wrap it for us.
async function wait(ms: number) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

afterEach(() => {
  // `resetAllMocks`, not `clearAllMocks`: a test that fails partway through
  // (as the very first run of this file is expected to, pre-fix) can leave
  // queued `mockResolvedValueOnce`/`mockRejectedValueOnce` entries
  // unconsumed. `clearAllMocks` only resets call history, not that queue,
  // which would otherwise leak into the next test.
  vi.resetAllMocks();
});

describe("useAnalysisDetail", () => {
  it(
    "keeps polling through a 404 sentinel and only stops once status is ready",
    async () => {
      mockedGetAnalysis
        .mockRejectedValueOnce(new ApiError("not found", 404))
        .mockRejectedValueOnce(new ApiError("not found", 404))
        .mockResolvedValueOnce(readyDetail);

      const { result } = renderHook(() => useAnalysisDetail("job-1"), { wrapper: createWrapper() });

      // Initial fetch settles as the null sentinel (404 -- not scheduled yet).
      await waitFor(() => expect(result.current.analysis).toBeNull());
      expect(mockedGetAnalysis).toHaveBeenCalledTimes(1);

      // A null sentinel must still be polled, exactly like an explicit
      // "pending" status -- this is the bug the reviewer found: `null?.status`
      // is `undefined`, not `"pending"`, so a naive refetchInterval check
      // would stop here instead of firing this second call.
      await waitFor(() => expect(mockedGetAnalysis).toHaveBeenCalledTimes(2), { timeout: 3000 });
      expect(result.current.analysis).toBeNull();

      // Third poll resolves to a real, ready row -- polling must stop here.
      await waitFor(() => expect(mockedGetAnalysis).toHaveBeenCalledTimes(3), { timeout: 3000 });
      await waitFor(() => expect(result.current.analysis?.status).toBe("ready"));

      // No further polling once the row is ready -- give it a full extra
      // interval and confirm nothing new fired.
      await wait(2300);
      expect(mockedGetAnalysis).toHaveBeenCalledTimes(3);
    },
    12_000,
  );

  it(
    "stops polling once the analysis has settled to failed",
    async () => {
      const failedDetail: AnalysisDetail = { ...readyDetail, status: "failed", overall_score: null };
      mockedGetAnalysis.mockResolvedValueOnce(failedDetail);

      const { result } = renderHook(() => useAnalysisDetail("job-1"), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.analysis?.status).toBe("failed"));

      await wait(2300);
      expect(mockedGetAnalysis).toHaveBeenCalledTimes(1);
    },
    6_000,
  );
});

describe("useAnalysisList", () => {
  it(
    "only polls while shouldPoll is true",
    async () => {
      mockedListAnalyses.mockResolvedValue([]);

      const { rerender } = renderHook(({ shouldPoll }: { shouldPoll: boolean }) => useAnalysisList(shouldPoll), {
        wrapper: createWrapper(),
        initialProps: { shouldPoll: false },
      });

      await waitFor(() => expect(mockedListAnalyses).toHaveBeenCalledTimes(1));

      // shouldPoll is false: no automatic refetch should be scheduled.
      await wait(2300);
      expect(mockedListAnalyses).toHaveBeenCalledTimes(1);

      rerender({ shouldPoll: true });

      await waitFor(() => expect(mockedListAnalyses).toHaveBeenCalledTimes(2), { timeout: 3000 });
    },
    8_000,
  );
});
