import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "./api/client";
import type { DocumentKind, DocumentSummary } from "./api/types";
import { AnalysisPane } from "./components/AnalysisPane";
import { ChatDock } from "./components/ChatDock";
import { JobRail } from "./components/JobRail";
import { TraceDrawer } from "./components/TraceDrawer";
import { WorkspaceEmptyState } from "./components/WorkspaceEmptyState";
import { shouldPollAnalysisList, useAnalysisDetail, useAnalysisList } from "./hooks/useAnalysis";
import { useDocuments } from "./hooks/useDocuments";
import { headingFor, toAnalysisView, toJobRailItem, withSelectedVerdictCounts } from "./view-models/analysis-adapters";
import type { AnalysisView, JobRailItem } from "./view-models/dashboard";

export function App() {
  const { documents, isLoading, error, upload, paste, busy } = useDocuments();
  const jobDocuments = useMemo(() => documents.filter((document) => document.kind === "job"), [documents]);

  // useAnalysisList's own refetchInterval option needs, on this render,
  // whether anything could still change -- which in turn depends on the
  // analyses data this very call returns. A ref carries the previous
  // render's answer forward as this render's poll decision, then is
  // refreshed immediately below for the *next* render; the lag this
  // introduces is at most one re-render, and useDocuments's own 2s poll
  // (firing whenever any job is still mid-extraction) guarantees one keeps
  // happening on its own while anything is in flight.
  const shouldPollAnalysesRef = useRef(true);
  const analysisList = useAnalysisList(shouldPollAnalysesRef.current);
  shouldPollAnalysesRef.current = shouldPollAnalysisList(jobDocuments, analysisList.analyses);

  const [problem, setProblem] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const analysisDetail = useAnalysisDetail(selectedJobId);
  const resumeInput = useRef<HTMLInputElement>(null);
  const resume = documents.find((document) => document.kind === "resume");

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
  const analysis = selectedDocument ? buildAnalysisView(selectedDocument, analysisDetail) : null;

  return (
    <main className="workspace">
      <input ref={resumeInput} type="file" className="sr-only" accept=".pdf,.docx,.txt,.md" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) handleUpload(file, "resume"); event.target.value = ""; }} />
      <TopBar jobCount={jobDocuments.length} />
      {(problem || error) && <div role="alert" className="global-alert">{problem ?? "Could not reach the API. Is it running?"}</div>}
      <div className="workspace-body">
        <JobRail
          resume={resume ? { filename: resume.filename ?? resume.title ?? "Pasted resume", detail: resumeDetail(resume) } : null}
          jobs={jobDocuments.map((document) => buildRailItem(document, selectedJobId, analysisList, analysisDetail))}
          selectedJobId={selectedJobId}
          onSelect={setSelectedJobId}
          onAddJob={() => handlePaste("job")}
        />
        <section className="center-column">
          {!resume ? <WorkspaceEmptyState onChooseFile={() => resumeInput.current?.click()} onFile={(file) => handleUpload(file, "resume")} onPaste={() => handlePaste("resume")} /> : analysis ? <AnalysisPane analysis={analysis} onPastePosting={() => handlePaste("job")} retryPending={analysisDetail.retry.isPending} /> : <NoJobState onAddJob={() => handlePaste("job")} />}
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

// A job is only ever waiting on the analyses API once its own extraction has
// succeeded -- pending/failed extraction states are decided from the
// document alone, before the adapters ever look at analysis data.
function dependsOnAnalysisData(document: DocumentSummary): boolean {
  return document.status !== "failed" && document.extraction_status === "ready";
}

// `isLoading`/`error` distinguish two real situations from a confirmed
// absence: the analyses API hasn't answered yet (first load), or it's
// unreachable while the documents API isn't (a genuine partial outage).
// Neither means "no analysis was ever scheduled" -- that's the adapter's
// job to say via a 404/missing-summary, which resolves to "analysing", not
// "unavailable". "unavailable" is reserved for these two loading/error
// cases, which is what keeps it from ever showing for a healthy backend.
function buildRailItem(
  document: DocumentSummary,
  selectedJobId: string | undefined,
  analysisList: ReturnType<typeof useAnalysisList>,
  analysisDetail: ReturnType<typeof useAnalysisDetail>,
): JobRailItem {
  if (dependsOnAnalysisData(document) && (analysisList.isLoading || analysisList.error)) {
    return { ...headingFor(document), state: "unavailable" };
  }

  const summary = analysisList.analyses.find((entry) => entry.job_doc_id === document.id);
  const item = toJobRailItem(document, summary);
  return document.id === selectedJobId ? withSelectedVerdictCounts(item, analysisDetail.analysis) : item;
}

function buildAnalysisView(
  document: DocumentSummary,
  analysisDetail: ReturnType<typeof useAnalysisDetail>,
): AnalysisView {
  if (dependsOnAnalysisData(document) && (analysisDetail.isLoading || analysisDetail.error)) {
    return { status: "unavailable", job: headingFor(document) };
  }

  return toAnalysisView(document, analysisDetail.analysis, () => analysisDetail.retry.mutate());
}

function resumeDetail(document: DocumentSummary): string {
  if (document.status === "failed") return "Resume could not be parsed";
  if (document.extraction_status === "pending") return "Indexing resume spans…";
  if (document.extraction_status === "failed") return "Text ready · structured extraction failed";
  return "Resume spans indexed";
}

function messageFor(cause: unknown, fallback: string): string { return cause instanceof ApiError ? cause.message : fallback; }
