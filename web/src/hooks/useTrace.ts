import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";

export function useTrace(requestId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["traces", requestId ?? "none"],
    queryFn: () => apiClient.getTrace(requestId as string),
    enabled: Boolean(requestId) && enabled,
    retry: false,
  });
}
