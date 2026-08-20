export type DocumentKind = "resume" | "job";
export type DocumentSource = "upload" | "paste";
export type ProcessingStatus = "pending" | "ready" | "failed";

/**
 * Mirrors the API's DocumentSummary.
 *
 * Two status fields, deliberately. `status` is settled during the upload
 * request, because parsing happens there -- so a document that appears in a
 * listing at all is already usable. `extraction_status` tracks the background
 * enrichment, and that is what the UI shows as "processing".
 */
export interface DocumentSummary {
  id: string;
  kind: DocumentKind;
  source: DocumentSource;
  title: string | null;
  company: string | null;
  filename: string | null;
  status: ProcessingStatus;
  extraction_status: ProcessingStatus;
  created_at: string;
}

export interface PasteInput {
  kind: DocumentKind;
  text: string;
  title?: string;
  company?: string;
}
