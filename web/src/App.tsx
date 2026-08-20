import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "./api/client";
import type { DocumentKind, DocumentSummary } from "./api/types";
import { AnalysisPane } from "./components/AnalysisPane";
import { ChatDock } from "./components/ChatDock";
import { JobRail } from "./components/JobRail";
import { TraceDrawer } from "./components/TraceDrawer";
import { WorkspaceEmptyState } from "./components/WorkspaceEmptyState";
import { useDocuments } from "./hooks/useDocuments";
import type { AnalysisView, JobRailItem } from "./view-models/dashboard";

export function App() {
  const { documents, isLoading, error, upload, paste, busy } = useDocuments();
  const [problem, setProblem] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const resumeInput = useRef<HTMLInputElement>(null);
  const resume = documents.find((document) => document.kind === "resume");
  const jobDocuments = useMemo(() => documents.filter((document) => document.kind === "job"), [documents]);

  useEffect(() => {
    if (!jobDocuments.some((document) => document.id === selectedJobId)) setSelectedJobId(jobDocuments[0]?.id);
  }, [jobDocuments, selectedJobId]);

  const handleUpload = (file: File, kind: DocumentKind) => {
    setProblem(null);
    upload.mutate({ file, kind }, { onError: (cause) => setProblem(messageFor(cause, "Upload failed.")) });
  };

  const handlePaste = (kind: DocumentKind) => {
    const text = window.prompt(kind === "resume" ? "Paste your resume text" : "Paste the job posting");
    if (!text?.trim()) return;
    setProblem(null);
    paste.mutate({ kind, text }, { onError: (cause) => setProblem(messageFor(cause, "Could not save that text.")) });
  };

  if (isLoading) return <div className="app-loading"><span className="brand-mark" />Loading workspace…</div>;

  const selectedDocument = jobDocuments.find((document) => document.id === selectedJobId);
  const analysis = selectedDocument ? toAnalysisView(selectedDocument) : null;

  return (
    <main className="workspace">
      <input ref={resumeInput} type="file" className="sr-only" accept=".pdf,.docx,.txt,.md" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) handleUpload(file, "resume"); event.target.value = ""; }} />
      <TopBar jobCount={jobDocuments.length} />
      {(problem || error) && <div role="alert" className="global-alert">{problem ?? "Could not reach the API. Is it running?"}</div>}
      <div className="workspace-body">
        <JobRail
          resume={resume ? { filename: resume.filename ?? resume.title ?? "Pasted resume", detail: resumeDetail(resume) } : null}
          jobs={jobDocuments.map(toRailItem)}
          selectedJobId={selectedJobId}
          onSelect={setSelectedJobId}
          onAddJob={() => handlePaste("job")}
        />
        <section className="center-column">
          {!resume ? <WorkspaceEmptyState onChooseFile={() => resumeInput.current?.click()} onFile={(file) => handleUpload(file, "resume")} onPaste={() => handlePaste("resume")} /> : analysis ? <AnalysisPane analysis={analysis} /> : <NoJobState onAddJob={() => handlePaste("job")} />}
          <TraceDrawer connected={false} />
        </section>
        <ChatDock
          jobCompany={selectedDocument ? selectedDocument.company ?? selectedDocument.title ?? "this job" : undefined}
          jobCount={jobDocuments.filter((document) => document.extraction_status === "ready").length}
          requirementCount={0}
          connected={false}
          forceAllJobs={selectedDocument?.extraction_status === "failed" || selectedDocument?.status === "failed"}
          excludedJob={selectedDocument && (selectedDocument.extraction_status === "failed" || selectedDocument.status === "failed") ? selectedDocument.company ?? selectedDocument.title ?? "Selected job" : undefined}
        />
      </div>
    </main>
  );
}

function TopBar({ jobCount }: { jobCount: number }) {
  return <header className="top-bar"><div><span className="brand-mark" /><strong>Career Intelligence</strong><span className="top-meta">v0.4 · workspace</span></div><div><span>{jobCount} {jobCount === 1 ? "job" : "jobs"}</span><span className="top-divider" /><button type="button" disabled>Re-run all</button></div></header>;
}

function NoJobState({ onAddJob }: { onAddJob: () => void }) {
  return <section className="empty-state"><div className="empty-card no-job-card"><p className="eyebrow">Resume indexed</p><h1>Add the first job</h1><p>Paste a posting to extract its requirements and prepare it for fit analysis.</p><button type="button" className="primary-action" onClick={onAddJob}>Add job posting</button></div></section>;
}

function toRailItem(document: DocumentSummary): JobRailItem {
  const base = { id: document.id, title: document.title ?? document.filename ?? "Untitled role", company: document.company ?? "Company not specified" };
  if (document.status === "failed" || document.extraction_status === "failed") return { ...base, state: "failed" };
  if (document.extraction_status === "pending") return { ...base, state: "analysing" };
  return { ...base, state: "unavailable" };
}

function toAnalysisView(document: DocumentSummary): AnalysisView {
  const job = { id: document.id, title: document.title ?? document.filename ?? "Untitled role", company: document.company ?? "Company not specified" };
  if (document.status === "failed" || document.extraction_status === "failed") return { status: "extraction-failed", job };
  if (document.extraction_status === "pending") return { status: "analysing", job };
  return { status: "unavailable", job };
}

function resumeDetail(document: DocumentSummary): string {
  if (document.status === "failed") return "Resume could not be parsed";
  if (document.extraction_status === "pending") return "Indexing resume spans…";
  if (document.extraction_status === "failed") return "Text ready · structured extraction failed";
  return "Resume spans indexed";
}

function messageFor(cause: unknown, fallback: string): string { return cause instanceof ApiError ? cause.message : fallback; }
