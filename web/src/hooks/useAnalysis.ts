import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiClient } from "../api/client";
import type { AnalysisDetail, AnalysisSummary, DocumentSummary } from "../api/types";

const ANALYSES_KEY = ["analyses"] as const;
const POLL_INTERVAL_MS = 2000;

function analysisDetailKey(jobDocId: string) {
  return [...ANALYSES_KEY, jobDocId] as const;
}

/**
 * @param shouldPoll Same shape as `useDocuments`'s `hasPendingEnrichment`
 * pattern: the caller decides, from the full picture of documents +
 * analyses it can see, whether anything could still change server-side.
 * The list endpoint itself carries no per-entry progress (it's deliberately
 * minimal -- see the API brief), so this hook can't decide that on its own;
 * without a caller-driven poll nothing ever invalidates this query after
 * first load (the only other invalidation anywhere is the retry mutation's
 * own `onSuccess`), and a newly-appeared or newly-settled row would never
 * surface in the job rail short of a full page reload.
 */
export function useAnalysisList(shouldPoll: boolean) {
  const query = useQuery({
    queryKey: ANALYSES_KEY,
    queryFn: apiClient.listAnalyses,
    refetchInterval: shouldPoll ? POLL_INTERVAL_MS : false,
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
    // poll while the fetched row is still "pending", stop once it settles
    // into "ready" or "failed". The `null` sentinel (a 404 -- no row exists
    // yet, e.g. because the resume hasn't finished indexing or
    // schedule_fit_analyses hasn't claimed this pair yet) must be treated
    // the same as "pending", not stopped on: `null?.status` is `undefined`,
    // not `"pending"`, so checking only for that string would stop polling
    // on the very first 404 and never retry.
    refetchInterval: (query) => {
      const data = query.state.data;
      return data === undefined || data === null || data.status === "pending"
        ? POLL_INTERVAL_MS
        : false;
    },
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

/**
 * Bulk retry behind the top bar's one action. Deliberately built on the
 * same per-job endpoint as `useAnalysisDetail`'s `retry` rather than a
 * bulk one: the API refuses to recompute an analysis that is not
 * `failed` (analyses.py `_require_failed_analysis`), because recomputing a
 * good one costs money and can silently change verdicts. This retries the
 * failures and nothing else.
 *
 * Two consequences of that endpoint, both handled here:
 *
 * - The candidate list comes from the analyses list query, which can be up
 *   to one poll interval stale. A job that has since stopped being failed
 *   answers 409 -- which is the state this button was trying to reach, not
 *   an error to report.
 * - Every request is settled before anything is reported, so one job's
 *   rejection cannot abandon the jobs queued behind it.
 */
export function useRetryFailedAnalyses() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (jobDocIds: string[]) => {
      const results = await Promise.allSettled(
        jobDocIds.map((jobDocId) => apiClient.retryAnalysis(jobDocId)),
      );

      const rejected = results.filter(
        (result): result is PromiseRejectedResult =>
          result.status === "rejected" &&
          !(result.reason instanceof ApiError && result.reason.status === 409),
      );

      const [firstRejection] = rejected;
      if (firstRejection) throw firstRejection.reason;
    },
    // onSettled, not onSuccess: a partial failure still means some
    // analyses flipped to pending server-side, so the rail has to refetch
    // either way.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ANALYSES_KEY }),
  });
}

/**
 * Mirrors `useDocuments`'s `hasPendingEnrichment`: a pure predicate the
 * caller (`App.tsx`) evaluates from the full picture it can see, to decide
 * whether `useAnalysisList` still has something to wait for. Three
 * independent reasons the list could still change:
 *
 * - a job document hasn't finished extraction yet, so it hasn't even
 *   become eligible for `schedule_fit_analyses` to claim;
 * - a claimed pair is still being scored (`status === "pending"`);
 * - a job finished extraction but no `fit_analyses` row for it has shown up
 *   in the list yet at all -- extraction is done, but the (resume, job)
 *   pair hasn't been claimed/scored, which the list endpoint represents as
 *   the row simply being absent rather than a "pending" entry.
 */
export function shouldPollAnalysisList(
  jobDocuments: DocumentSummary[],
  analyses: AnalysisSummary[],
): boolean {
  if (jobDocuments.some((document) => document.extraction_status !== "ready")) return true;
  if (analyses.some((entry) => entry.status === "pending")) return true;

  const listedJobIds = new Set(analyses.map((entry) => entry.job_doc_id));
  return jobDocuments.some(
    (document) => document.extraction_status === "ready" && !listedJobIds.has(document.id),
  );
}
