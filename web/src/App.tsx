import { useState } from "react";

import { ApiError } from "./api/client";
import type { DocumentKind } from "./api/types";
import { UploadPanel } from "./components/UploadPanel";
import { useDocuments } from "./hooks/useDocuments";

export function App() {
  const { documents, isLoading, error, upload, paste, busy } = useDocuments();
  const [problem, setProblem] = useState<string | null>(null);

  const handleUpload = (file: File, kind: DocumentKind) => {
    setProblem(null);
    upload.mutate(
      { file, kind },
      {
        // The API explains itself on 415 and 422 -- an unsupported type, or a
        // scanned PDF with no text layer. Showing that text is the difference
        // between the user fixing it and the user guessing.
        onError: (cause) =>
          setProblem(cause instanceof ApiError ? cause.message : "Upload failed."),
      },
    );
  };

  const handlePaste = (kind: DocumentKind) => {
    const text = window.prompt(
      kind === "resume" ? "Paste your resume text" : "Paste the job posting",
    );
    if (!text?.trim()) return;

    setProblem(null);
    paste.mutate(
      { kind, text },
      {
        onError: (cause) =>
          setProblem(cause instanceof ApiError ? cause.message : "Could not save that text."),
      },
    );
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Career Intelligence</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload a resume and the roles you are considering.
        </p>
      </header>

      {problem && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {problem}
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-700">
          Could not reach the API. Is it running?
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <UploadPanel
          documents={documents}
          onUpload={handleUpload}
          onPaste={handlePaste}
          busy={busy}
        />
      )}
    </main>
  );
}
