import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiClient } from "../api/client";
import type { PrepDetail } from "../api/types";

const PREP_KEY = ["prep"] as const;

function prepKey(jobDocId: string | undefined) {
  return [...PREP_KEY, jobDocId ?? "none"] as const;
}

/**
 * `undefined` means "no data yet" (still loading, or disabled). `null`
 * means a confirmed 404 -- no interview prep has been generated yet for
 * this job. Mirrors `useAnalysisDetail`'s own `null`-vs-`undefined`
 * contract in `useAnalysis.ts`.
 *
 * `enabled` gates both the GET query and the auto-generate effect below --
 * the caller (`App.tsx`) passes whether the dashboard's ready view is
 * actually showing for this job, since prep only makes sense once the fit
 * analysis itself is `"ready"` (`analysis/service.py`'s own precondition,
 * enforced server-side as a 409 for anything else).
 *
 * The POST is triggered once, automatically, "on first open": as soon as
 * the GET has resolved to a confirmed absence (`null`) for the current
 * `jobDocId` and nothing is already in flight. `triggeredForJobRef` is what
 * makes a second open -- a re-render, or a re-selection of the same job
 * once the GET has come back with real data instead of `null` -- issue no
 * POST: the ref only re-arms when `jobDocId` itself changes.
 */
export function usePrep(jobDocId: string | undefined, options: { enabled: boolean }) {
  const { enabled } = options;
  const queryClient = useQueryClient();
  const triggeredForJobRef = useRef<string | undefined>(undefined);

  const query = useQuery({
    queryKey: prepKey(jobDocId),
    queryFn: async (): Promise<PrepDetail | null> => {
      try {
        return await apiClient.getPrep(jobDocId as string);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) return null;
        throw cause;
      }
    },
    enabled: Boolean(jobDocId) && enabled,
  });

  const generate = useMutation({
    mutationFn: () => apiClient.generatePrep(jobDocId as string),
    onSuccess: (detail) => {
      queryClient.setQueryData(prepKey(jobDocId), detail);
    },
  });

  const generateMutate = generate.mutate;

  useEffect(() => {
    if (!jobDocId || !enabled) return;
    // undefined: the GET hasn't resolved yet. A real PrepDetail: already
    // cached, nothing to do. Only a confirmed 404 (null) triggers generation.
    if (query.data === undefined || query.data !== null) return;
    if (triggeredForJobRef.current === jobDocId) return;

    triggeredForJobRef.current = jobDocId;
    generateMutate();
  }, [jobDocId, enabled, query.data, generateMutate]);

  return {
    prep: query.data,
    isLoading: query.isLoading,
    error: query.error,
    generate,
  };
}
