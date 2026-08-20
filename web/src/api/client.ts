import type { DocumentKind, DocumentSummary, PasteInput } from "./types";

const BASE = "/api";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  // FastAPI puts a human-readable reason in `detail` -- the parser raises it
  // for scanned PDFs and unsupported types, so surfacing it verbatim tells the
  // user what to do instead of "request failed".
  let detail = response.statusText;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // Non-JSON error body; the status text stands.
  }

  throw new ApiError(detail, response.status);
}

export const apiClient = {
  async uploadDocument(file: File, kind: DocumentKind): Promise<DocumentSummary> {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);

    return unwrap<DocumentSummary>(
      await fetch(`${BASE}/documents/upload`, { method: "POST", body: form }),
    );
  },

  async pasteDocument(input: PasteInput): Promise<DocumentSummary> {
    return unwrap<DocumentSummary>(
      await fetch(`${BASE}/documents/paste`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    );
  },

  async listDocuments(): Promise<DocumentSummary[]> {
    return unwrap<DocumentSummary[]>(await fetch(`${BASE}/documents`));
  },

  async deleteDocument(id: string): Promise<void> {
    return unwrap<void>(await fetch(`${BASE}/documents/${id}`, { method: "DELETE" }));
  },
};

export { ApiError };
