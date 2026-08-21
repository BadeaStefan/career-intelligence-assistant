import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";

const CONFIG_KEY = ["config"] as const;

/**
 * Server-owned configuration.
 *
 * Never polled: these values are fixed for the lifetime of the API process,
 * so a change to them arrives with a restart, which ends this session anyway.
 */
export function useConfig() {
  const query = useQuery({
    queryKey: CONFIG_KEY,
    queryFn: apiClient.getConfig,
    staleTime: Infinity,
  });

  // Undefined until the request lands, and left undefined if it fails. The
  // consumer omits what it cannot state truthfully rather than substituting a
  // default that would contradict the server.
  return { maxUploadBytes: query.data?.max_upload_bytes };
}
