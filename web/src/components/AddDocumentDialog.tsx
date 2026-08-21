import { useEffect, useRef, useState } from "react";

import type { DocumentKind } from "../api/types";
import { formatBytes } from "../view-models/format";

/**
 * The one way documents get added, for either kind.
 *
 * It replaces a `window.prompt`, which could not show the size limit, could
 * not report an error without throwing away what had been typed, and offered
 * no way to attach a file -- so job postings could only ever arrive as text
 * even though the upload endpoint has always accepted `kind=job`.
 *
 * Presentational: it neither fetches nor mutates, so every state that matters
 * (rejected file, server error, busy) is reachable in a test without a server.
 */

/** Mirrors `SUPPORTED_TYPES` in `api/src/career_intel/ingest/parsing.py`. */
const SUPPORTED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
  "application/octet-stream",
]);

/**
 * Why the client checks at all: without it an oversized PDF makes a full
 * round trip before the server's 413 comes back.
 *
 * Why it checks only the content type, never the extension: the server
 * dispatches on content type on purpose (a PDF named `.txt` would otherwise
 * reach the text decoder and yield mojibake that looks like a successful
 * parse), and a client that disagreed would refuse files the server accepts.
 * An empty `file.type` -- which browsers report for plenty of ordinary files
 * -- is left alone for the same reason: `fetch` sends it as
 * `application/octet-stream`, which is on the server's allowlist.
 */
export function rejectReason(file: File, maxUploadBytes?: number): string | null {
  if (maxUploadBytes !== undefined && file.size > maxUploadBytes) {
    return `That file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxUploadBytes)}.`;
  }

  if (file.type && !SUPPORTED_TYPES.has(file.type)) {
    return `${file.name} is not a type that can be read. Use a PDF, DOCX, or plain text file.`;
  }

  return null;
}

interface AddDocumentDialogProps {
  /** The kind being added, or `null` when the dialog is closed. */
  kind: DocumentKind | null;
  onClose: () => void;
  onSubmitFile: (file: File) => void;
  onSubmitText: (input: { text: string; title?: string; company?: string }) => void;
  /** Undefined until `/config` answers. No fallback -- see WorkspaceEmptyState. */
  maxUploadBytes?: number;
  busy?: boolean;
  serverError?: string | null;
}

export function AddDocumentDialog(props: AddDocumentDialogProps) {
  // Remounting per open is deliberate: it clears the textarea, the metadata
  // fields and any local rejection without a reset effect to keep in sync.
  return props.kind === null ? null : <OpenDialog {...props} kind={props.kind} />;
}

function OpenDialog({
  kind,
  onClose,
  onSubmitFile,
  onSubmitText,
  maxUploadBytes,
  busy = false,
  serverError,
}: AddDocumentDialogProps & { kind: DocumentKind }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [rejected, setRejected] = useState<string | null>(null);

  // `showModal` rather than the `open` attribute: it is what gives the
  // backdrop, the focus trap and Esc-to-close, none of which are worth
  // reimplementing.
  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const isJob = kind === "job";
  const noun = isJob ? "job posting" : "resume";
  const problem = rejected ?? serverError ?? null;

  const takeFile = (file: File | undefined) => {
    if (!file) return;

    const reason = rejectReason(file, maxUploadBytes);
    setRejected(reason);
    if (!reason) onSubmitFile(file);
  };

  const submitText = () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setRejected(null);
    onSubmitText({
      text: trimmed,
      title: title.trim() || undefined,
      company: company.trim() || undefined,
    });
  };

  return (
    <dialog ref={dialog} className="add-dialog" aria-labelledby="add-dialog-heading" onCancel={onClose} onClose={onClose}>
      <h2 id="add-dialog-heading">Add {noun}</h2>

      <div
        className="dropzone"
        data-testid="add-dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          takeFile(event.dataTransfer.files[0]);
        }}
      >
        <p>Drop a PDF or DOCX here</p>
        <span>
          or{" "}
          <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>
            choose a file
          </button>
          {maxUploadBytes !== undefined && ` · max ${formatBytes(maxUploadBytes)}`}
        </span>
        <input
          ref={fileInput}
          type="file"
          className="sr-only"
          accept=".pdf,.docx,.txt,.md"
          disabled={busy}
          onChange={(event) => {
            takeFile(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>

      <div className="or-divider">
        <span />
        <em>or</em>
        <span />
      </div>

      {isJob && (
        <div className="add-dialog-meta">
          <label>
            Title
            <input value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} placeholder="Senior Backend Engineer" />
          </label>
          <label>
            Company
            <input value={company} disabled={busy} onChange={(event) => setCompany(event.target.value)} placeholder="Datadog" />
          </label>
        </div>
      )}

      <label className="add-dialog-text">
        {isJob ? "Job posting text" : "Resume text"}
        <textarea
          rows={8}
          value={text}
          disabled={busy}
          placeholder={isJob ? "Paste the posting…" : "Paste your resume…"}
          onChange={(event) => setText(event.target.value)}
        />
      </label>

      {problem && (
        <p role="alert" className="add-dialog-problem">
          {problem}
        </p>
      )}

      <div className="add-dialog-actions">
        <button type="button" className="secondary-action" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="primary-action" disabled={busy || !text.trim()} onClick={submitText}>
          Add {isJob ? "job" : "resume"}
        </button>
      </div>
    </dialog>
  );
}
