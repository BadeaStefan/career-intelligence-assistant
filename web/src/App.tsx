import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "./api/client";
import type { DocumentKind, DocumentSummary } from "./api/types";
import { AddDocumentDialog } from "./components/AddDocumentDialog";
import { AnalysisPane } from "./components/AnalysisPane";
import { ChatDock } from "./components/ChatDock";
import { JobRail } from "./components/JobRail";
import { TraceDrawer } from "./components/TraceDrawer";
import { WorkspaceEmptyState } from "./components/WorkspaceEmptyState";
import { shouldPollAnalysisList, useAnalysisDetail, useAnalysisList } from "./hooks/useAnalysis";
import { useChat } from "./hooks/useChat";
import { useConfig } from "./hooks/useConfig";
import { useDocuments } from "./hooks/useDocuments";
import { usePrep } from "./hooks/usePrep";
import { useTrace } from "./hooks/useTrace";
import { headingFor, toAnalysisView, toJobRailItem, withSelectedVerdictCounts } from "./view-models/analysis-adapters";
import type { AnalysisView, JobRailItem } from "./view-models/dashboard";

export function App() {
  const { documents, isLoading, error, upload, paste, busy } = useDocuments();
  const { maxUploadBytes } = useConfig();
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
  // The kind currently being added, or null for "dialog closed". Two error
  // slots, not one: a failure raised while the dialog is open belongs inside
  // it, next to the text the user would otherwise have to retype, while
  // everything else belongs on the global bar.
  const [addKind, setAddKind] = useState<DocumentKind | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const analysisDetail = useAnalysisDetail(selectedJobId);
  // Prep only makes sense once the fit analysis itself is "ready" (the
  // server 409s POST /prep for anything else) -- gating usePrep's query and
  // its auto-generate effect on that keeps a pending/failed job from ever
  // firing a doomed POST.
  const prep = usePrep(selectedJobId, { enabled: analysisDetail.analysis?.status === "ready" });
  const resumeInput = useRef<HTMLInputElement>(null);
  const resume = documents.find((document) => document.kind === "resume");
  const chat = useChat(selectedJobId);
  const [traceOpen, setTraceOpen] = useState(false);
  const trace = useTrace(chat.requestId, traceOpen);

  // Chat retrieval reads resume *chunks*, produced in the same background
  // ingest pass as structured extraction (ingest/pipeline.py: chunks are
  // committed unconditionally, even when extraction itself later fails and
  // extraction_status settles to "failed" -- see that module's docstring on
  // degrading to chunk-only RAG). So chat is ready once that pass has run
  // at all, not only once it has fully succeeded: "pending" is the one
  // status that means no chunks exist yet.
  const chatConnected = Boolean(resume) && resume?.extraction_status !== "pending";

  useEffect(() => {
    if (!jobDocuments.some((document) => document.id === selectedJobId)) setSelectedJobId(jobDocuments[0]?.id);
  }, [jobDocuments, selectedJobId]);

  const handleUpload = (file: File, kind: DocumentKind) => {
    setProblem(null);
    upload.mutate({ file, kind }, { onError: (cause) => setProblem(messageFor(cause, "Upload failed.")) });
  };

  const openAdd = (kind: DocumentKind) => {
    setProblem(null);
    setDialogError(null);
    setAddKind(kind);
  };

  const handleDialogFile = (file: File) => {
    if (!addKind) return;
    setDialogError(null);
    upload.mutate(
      { file, kind: addKind },
      { onSuccess: () => setAddKind(null), onError: (cause) => setDialogError(messageFor(cause, "Upload failed.")) },
    );
  };

  const handleDialogText = (input: { text: string; title?: string; company?: string }) => {
    if (!addKind) return;
    setDialogError(null);
    paste.mutate(
      { kind: addKind, ...input },
      { onSuccess: () => setAddKind(null), onError: (cause) => setDialogError(messageFor(cause, "Could not save that text.")) },
    );
  };

  if (isLoading) return <div className="app-loading"><span className="brand-mark" />Loading workspace…</div>;

  const selectedDocument = jobDocuments.find((document) => document.id === selectedJobId);
  const analysis = selectedDocument ? buildAnalysisView(selectedDocument, analysisDetail, prep) : null;

  return (
    <main className="workspace">
      <input ref={resumeInput} type="file" className="sr-only" accept=".pdf,.docx,.txt,.md" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) handleUpload(file, "resume"); event.target.value = ""; }} />
      <AddDocumentDialog
        kind={addKind}
        onClose={() => setAddKind(null)}
        onSubmitFile={handleDialogFile}
        onSubmitText={handleDialogText}
        maxUploadBytes={maxUploadBytes}
        busy={busy}
        serverError={dialogError}
      />
      <TopBar jobCount={jobDocuments.length} />
      {(problem || error) && <div role="alert" className="global-alert">{problem ?? "Could not reach the API. Is it running?"}</div>}
      <div className="workspace-body">
        <JobRail
          resume={resume ? { filename: resume.filename ?? resume.title ?? "Pasted resume", detail: resumeDetail(resume) } : null}
          jobs={jobDocuments.map((document) => buildRailItem(document, selectedJobId, analysisList, analysisDetail))}
          selectedJobId={selectedJobId}
          onSelect={setSelectedJobId}
          onAddJob={() => openAdd("job")}
        />
        <section className="center-column">
          {!resume ? <WorkspaceEmptyState onChooseFile={() => resumeInput.current?.click()} onFile={(file) => handleUpload(file, "resume")} onPaste={() => openAdd("resume")} maxUploadBytes={maxUploadBytes} /> : analysis ? (
            <AnalysisPane
              analysis={analysis}
              onPastePosting={() => openAdd("job")}
              retryPending={analysisDetail.retry.isPending}
              prepGenerationFailed={prep.isGenerateError}
              onRetryPrep={() => prep.generate.mutate()}
              prepRetryPending={prep.generate.isPending}
              // Both halves of "prep is on its way": the GET that decides
              // whether anything exists yet, and the POST usePrep fires
              // automatically once that GET confirms a 404. Either one in
              // flight means the tab must not claim questions are waiting on
              // a fit analysis that has, by this point, already finished.
              prepGenerating={prep.generate.isPending || prep.isLoading}
            />
          ) : <NoJobState onAddJob={() => openAdd("job")} />}
          <TraceDrawer
            open={traceOpen}
            onOpenChange={setTraceOpen}
            requestId={chat.requestId}
            trace={trace.data}
            loading={trace.isLoading && trace.fetchStatus === "fetching"}
            error={trace.isError}
          />
        </section>
        <ChatDock
          jobCompany={selectedDocument ? selectedDocument.company ?? selectedDocument.title ?? "this job" : undefined}
          jobCount={jobDocuments.filter((document) => document.extraction_status === "ready").length}
          requirementCount={0}
          connected={chatConnected}
          forceAllJobs={selectedDocument?.extraction_status === "failed" || selectedDocument?.status === "failed"}
          excludedJob={selectedDocument && (selectedDocument.extraction_status === "failed" || selectedDocument.status === "failed") ? selectedDocument.company ?? selectedDocument.title ?? "Selected job" : undefined}
          messages={chat.messages}
          sending={chat.sendMessage.isPending}
          onSend={(content, scope) => {
            setProblem(null);
            chat.sendMessage.mutate(
              { content, scope },
              { onError: (cause) => setProblem(messageFor(cause, "Could not send that message.")) },
            );
          }}
        />
      </div>
    </main>
  );
}

function TopBar({ jobCount }: { jobCount: number }) {
  return <header className="top-bar"><div><span className="brand-mark" /><strong>Career Intelligence</strong><span className="top-meta">v0.4 · workspace</span></div><div><span>{jobCount} {jobCount === 1 ? "job" : "jobs"}</span><span className="top-divider" /><button type="button" disabled>Re-run all</button></div></header>;
}

function NoJobState({ onAddJob }: { onAddJob: () => void }) {
  return <section className="empty-state"><div className="empty-card no-job-card"><p className="eyebrow">Resume indexed</p><h1>Add the first job</h1><p>Upload a PDF or DOCX, or paste the text. Either way its requirements are extracted and prepared for fit analysis.</p><button type="button" className="primary-action" onClick={onAddJob}>Add job posting</button></div></section>;
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
  prep: ReturnType<typeof usePrep>,
): AnalysisView {
  if (dependsOnAnalysisData(document) && (analysisDetail.isLoading || analysisDetail.error)) {
    return { status: "unavailable", job: headingFor(document) };
  }

  return toAnalysisView(document, analysisDetail.analysis, () => analysisDetail.retry.mutate(), prep.prep);
}

function resumeDetail(document: DocumentSummary): string {
  if (document.status === "failed") return "Resume could not be parsed";
  if (document.extraction_status === "pending") return "Indexing resume spans…";
  if (document.extraction_status === "failed") return "Text ready · structured extraction failed";
  return "Resume spans indexed";
}

function messageFor(cause: unknown, fallback: string): string { return cause instanceof ApiError ? cause.message : fallback; }
