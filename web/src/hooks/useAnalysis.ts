import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiClient } from "../api/client";
import type { AnalysisDetail } from "../api/types";

const ANALYSES_KEY = ["analyses"] as const;
const POLL_INTERVAL_MS = 2000;

function analysisDetailKey(jobDocId: string) {
  return [...ANALYSES_KEY, jobDocId] as const;
}

export function useAnalysisList() {
  const query = useQuery({
    queryKey: ANALYSES_KEY,
    queryFn: apiClient.listAnalyses,
    // No per-entry progress lives here (the list endpoint is deliberately
    // minimal -- see the API brief); an individual job's own pending state
    // is tracked by useAnalysisDetail once it is selected, so this list
    // doesn't need to poll on its own.
  });

  return {
    analyses: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
  };
}

/**
 * `undefined` means "no data yet" (still loading, or disabled because no
 * job is selected). `null` means a confirmed 404 -- no fit_analyses row
 * exists yet for this job. An `AnalysisDetail` means a resolved row, which
 * may itself be "pending", "ready", or "failed".
 */
export function useAnalysisDetail(jobDocId: string | undefined) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: analysisDetailKey(jobDocId ?? "none"),
    queryFn: async (): Promise<AnalysisDetail | null> => {
      try {
        return await apiClient.getAnalysis(jobDocId as string);
      } catch (cause) {
        // A 404 means "not scheduled yet" -- an expected, handleable
        // outcome (see apiClient.getAnalysis), not a request failure. It is
        // returned as query data (the sentinel `null`) rather than left to
        // fall into TanStack Query's generic error state.
        if (cause instanceof ApiError && cause.status === 404) return null;
        throw cause;
      }
    },
    enabled: Boolean(jobDocId),
    // Same shape as useDocuments's hasPendingEnrichment-driven interval:
    // poll only while the fetched row is still "pending", stop once it
    // settles into "ready" or "failed" (or was never scheduled -- null).
    refetchInterval: (query) => (query.state.data?.status === "pending" ? POLL_INTERVAL_MS : false),
  });

  const retry = useMutation({
    mutationFn: () => apiClient.retryAnalysis(jobDocId as string),
    // Invalidating the shared "analyses" prefix covers both this job's
    // detail query and the rail's list query in one call -- the list's
    // "failed" row should flip to "pending" too once the retry lands.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ANALYSES_KEY }),
  });

  return {
    analysis: query.data,
    isLoading: query.isLoading,
    error: query.error,
    retry,
  };
}
