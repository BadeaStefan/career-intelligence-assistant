import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { DocumentKind, DocumentSummary, PasteInput } from "../api/types";

const DOCUMENTS_KEY = ["documents"] as const;
const POLL_INTERVAL_MS = 2000;

export function useDocuments() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: DOCUMENTS_KEY,
    queryFn: apiClient.listDocuments,
    // Poll only while something is still being enriched. Enrichment is the
    // only asynchronous stage -- parsing already finished inside the upload
    // request -- so once nothing is pending there is nothing to wait for and
    // the polling stops on its own.
    refetchInterval: (query) =>
      hasPendingEnrichment(query.state.data) ? POLL_INTERVAL_MS : false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY });

  const upload = useMutation({
    mutationFn: ({ file, kind }: { file: File; kind: DocumentKind }) =>
      apiClient.uploadDocument(file, kind),
    onSuccess: invalidate,
  });

  const paste = useMutation({
    mutationFn: (input: PasteInput) => apiClient.pasteDocument(input),
    onSuccess: invalidate,
  });

  return {
    documents: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    upload,
    paste,
    busy: upload.isPending || paste.isPending,
  };
}

export function hasPendingEnrichment(documents: DocumentSummary[] | undefined): boolean {
  return (documents ?? []).some((doc) => doc.extraction_status === "pending");
}
