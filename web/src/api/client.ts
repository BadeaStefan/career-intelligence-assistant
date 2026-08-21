import type {
  AnalysisDetail,
  AnalysisSummary,
  ChatReply,
  ChatScope,
  ChatSessionSummary,
  ClientConfig,
  DocumentKind,
  DocumentSummary,
  MessageSummary,
  PasteInput,
  PrepDetail,
  TraceDetail,
  TracedChatReply,
} from "./types";

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
  // Server-owned limits the UI has to state. Fetched rather than hardcoded:
  // a literal here goes stale the moment MAX_UPLOAD_BYTES changes, and shows
  // the user a number the server will not honour.
  async getConfig(): Promise<ClientConfig> {
    return unwrap<ClientConfig>(await fetch(`${BASE}/config`));
  },

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

  async listAnalyses(): Promise<AnalysisSummary[]> {
    return unwrap<AnalysisSummary[]>(await fetch(`${BASE}/analyses`));
  },

  // A 404 here is a real, expected state (no fit_analyses row exists yet
  // for this job) -- it surfaces as a thrown ApiError with `.status === 404`
  // like any other error response, distinguishable by callers that need to
  // treat it as "not scheduled yet" rather than "request failed".
  async getAnalysis(jobDocId: string): Promise<AnalysisDetail> {
    return unwrap<AnalysisDetail>(await fetch(`${BASE}/analyses/${jobDocId}`));
  },

  async retryAnalysis(jobDocId: string): Promise<void> {
    return unwrap<void>(
      await fetch(`${BASE}/analyses/${jobDocId}/retry`, { method: "POST" }),
    );
  },

  // `jobDocId` is undefined for a dock with no job selected -- the session
  // is still created (scope "all" works with no job bound), just never
  // usable with scope "job" (the API 400s that combination -- see
  // chat/service.py).
  async createChatSession(jobDocId?: string): Promise<ChatSessionSummary> {
    return unwrap<ChatSessionSummary>(
      await fetch(`${BASE}/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_doc_id: jobDocId ?? null }),
      }),
    );
  },

  async sendChatMessage(
    sessionId: string,
    content: string,
    scope: ChatScope,
  ): Promise<TracedChatReply> {
    const response = await fetch(`${BASE}/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, scope }),
    });
    const reply = await unwrap<ChatReply>(response);
    return { ...reply, request_id: response.headers.get("X-Request-ID") };
  },

  async listChatMessages(sessionId: string): Promise<MessageSummary[]> {
    return unwrap<MessageSummary[]>(
      await fetch(`${BASE}/chat/sessions/${sessionId}/messages`),
    );
  },

  // A 404 here is a real, expected state (no interview prep generated yet
  // for this job) -- same "surfaces as ApiError.status === 404" contract as
  // getAnalysis above.
  async getPrep(jobDocId: string): Promise<PrepDetail> {
    return unwrap<PrepDetail>(await fetch(`${BASE}/prep/${jobDocId}`));
  },

  // Generation is a POST, never a GET (spec §7): a generating GET would be
  // non-idempotent, so callers that want "generate, or return the cached
  // row if one already exists" must call this, not getPrep.
  async generatePrep(jobDocId: string): Promise<PrepDetail> {
    return unwrap<PrepDetail>(
      await fetch(`${BASE}/prep/${jobDocId}`, { method: "POST" }),
    );
  },

  async getTrace(requestId: string): Promise<TraceDetail> {
    return unwrap<TraceDetail>(await fetch(`${BASE}/traces/${encodeURIComponent(requestId)}`));
  },
};

export { ApiError };
