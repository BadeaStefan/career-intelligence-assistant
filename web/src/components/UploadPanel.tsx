import type { DocumentKind, DocumentSummary, ProcessingStatus } from "../api/types";

interface UploadPanelProps {
  documents: DocumentSummary[];
  onUpload?: (file: File, kind: DocumentKind) => void;
  onPaste?: (kind: DocumentKind) => void;
  busy?: boolean;
}

/**
 * Lists ingested documents and offers the two ways in: upload or paste.
 *
 * Presentational on purpose -- it takes documents as a prop rather than
 * fetching them, so the states that matter (processing, failed analysis,
 * empty) are testable without a server or a query client.
 */
export function UploadPanel({ documents, onUpload, onPaste, busy = false }: UploadPanelProps) {
  const resumes = documents.filter((doc) => doc.kind === "resume");
  const jobs = documents.filter((doc) => doc.kind === "job");

  return (
    <section className="flex flex-col gap-6">
      <DocumentGroup
        heading="Resume"
        emptyHint="Upload your resume to get started."
        documents={resumes}
        kind="resume"
        onUpload={onUpload}
        onPaste={onPaste}
        busy={busy}
      />

      <DocumentGroup
        heading="Job postings"
        emptyHint="Add the roles you are considering."
        documents={jobs}
        kind="job"
        onUpload={onUpload}
        onPaste={onPaste}
        busy={busy}
      />

      {documents.length === 0 && (
        <p className="text-sm text-slate-500">
          No documents yet. Upload a resume and at least one job posting to see how you match.
        </p>
      )}
    </section>
  );
}

interface DocumentGroupProps {
  heading: string;
  emptyHint: string;
  documents: DocumentSummary[];
  kind: DocumentKind;
  onUpload?: (file: File, kind: DocumentKind) => void;
  onPaste?: (kind: DocumentKind) => void;
  busy: boolean;
}

function DocumentGroup({
  heading,
  emptyHint,
  documents,
  kind,
  onUpload,
  onPaste,
  busy,
}: DocumentGroupProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
          {heading}
        </h2>

        <div className="flex items-center gap-2">
          <label className="cursor-pointer text-xs text-slate-600 hover:text-slate-900">
            <input
              type="file"
              className="sr-only"
              accept=".pdf,.docx,.txt,.md"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onUpload?.(file, kind);
                event.target.value = "";
              }}
            />
            Upload
          </label>

          <button
            type="button"
            className="text-xs text-slate-600 hover:text-slate-900"
            disabled={busy}
            onClick={() => onPaste?.(kind)}
          >
            Paste
          </button>
        </div>
      </div>

      {documents.length === 0 ? (
        <p className="text-xs text-slate-400">{emptyHint}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {documents.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between rounded border border-slate-200 px-3 py-2"
            >
              <span className="truncate text-sm text-slate-800">
                {doc.title ?? doc.filename ?? "Untitled"}
              </span>
              <StatusBadge status={doc.status} extractionStatus={doc.extraction_status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusBadge({
  status,
  extractionStatus,
}: {
  status: ProcessingStatus;
  extractionStatus: ProcessingStatus;
}) {
  // status is checked first: if parsing itself failed the document is
  // unusable, which is a different and worse thing than enrichment failing.
  const { label, tone } = describe(status, extractionStatus);

  return <span className={`text-xs whitespace-nowrap ${tone}`}>{label}</span>;
}

function describe(
  status: ProcessingStatus,
  extractionStatus: ProcessingStatus,
): { label: string; tone: string } {
  if (status === "failed") {
    return { label: "Unusable", tone: "text-red-600" };
  }

  if (extractionStatus === "pending") {
    return { label: "Processing…", tone: "text-amber-600" };
  }

  if (extractionStatus === "failed") {
    // Deliberately not "failed" on its own. The text is stored and the
    // document is still answerable; only the structured records are missing.
    return { label: "Analysis failed", tone: "text-red-600" };
  }

  return { label: "Ready", tone: "text-emerald-600" };
}
