import { useMemo, useState } from "react";

import type { AnalysisView, RequirementView, Verdict } from "../view-models/dashboard";
import { PrepPane } from "./PrepPane";
import { RequirementRow } from "./RequirementRow";

export function AnalysisPane({
  analysis,
  onRetryExtraction,
  onPastePosting,
  retryPending,
  prepGenerationFailed,
  onRetryPrep,
  prepRetryPending,
  prepGenerating,
}: {
  analysis: AnalysisView;
  onRetryExtraction?: () => void;
  onPastePosting?: () => void;
  // Mirrors useDocuments's `busy` convention (`upload.isPending || paste.isPending`):
  // the caller passes the retry mutation's own `isPending` flag straight
  // through. Kept as a plain AnalysisPane prop rather than added to
  // AnalysisView -- that type is shared, adapter-built presentation state,
  // not a place for one mutation's live in-flight flag.
  retryPending?: boolean;
  // Same convention as retryPending, for usePrep's generate mutation: a
  // failed POST /prep must render as a distinct state from "not analysed
  // yet" (an empty prepQuestions array with no error), not the same
  // "questions will appear after fit analysis" copy PrepPane shows for
  // that -- see usePrep.ts's module docstring on why a failure alone
  // cannot re-arm itself without an explicit retry.
  prepGenerationFailed?: boolean;
  onRetryPrep?: () => void;
  prepRetryPending?: boolean;
  // Same convention again, for the third state the prep tab can be in.
  // "Not analysed yet" and "generating right now" are not the same thing:
  // POST /prep 409s unless the fit analysis is already ready, so while the
  // request is in flight PrepPane's "questions will appear after fit
  // analysis" copy states the opposite of what is true.
  prepGenerating?: boolean;
}) {
  if (analysis.status === "extraction-failed") return <ExtractionFailure analysis={analysis} onRetry={onRetryExtraction} onPaste={onPastePosting} />;
  if (analysis.status === "analysis-failed") return <AnalysisFailure analysis={analysis} retryPending={retryPending} />;
  if (analysis.status === "analysing") return <AnalysingState analysis={analysis} />;
  if (analysis.status === "unavailable") return <UnavailableState analysis={analysis} />;
  return (
    <ReadyAnalysis
      analysis={analysis}
      prepGenerationFailed={prepGenerationFailed}
      onRetryPrep={onRetryPrep}
      prepRetryPending={prepRetryPending}
      prepGenerating={prepGenerating}
    />
  );
}

function ReadyAnalysis({
  analysis,
  prepGenerationFailed,
  onRetryPrep,
  prepRetryPending,
  prepGenerating,
}: {
  analysis: Extract<AnalysisView, { status: "ready" }>;
  prepGenerationFailed?: boolean;
  onRetryPrep?: () => void;
  prepRetryPending?: boolean;
  prepGenerating?: boolean;
}) {
  const [tab, setTab] = useState<"analysis" | "prep">("analysis");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const grouped = useMemo(
    () => ({
      strong: analysis.requirements.filter((item) => item.verdict === "strong"),
      partial: analysis.requirements.filter((item) => item.verdict === "partial"),
      missing: analysis.requirements.filter((item) => item.verdict === "missing"),
    }),
    [analysis.requirements],
  );

  return (
    <section className="analysis-pane">
      <AnalysisHeader
        job={analysis.job}
        requirementCount={analysis.requirements.length}
        score={analysis.score}
        requirements={analysis.requirements}
        tab={tab}
        onTab={setTab}
      />
      <div className="analysis-scroll">
        {tab === "analysis" ? (
          <div className="requirements-list">
            {(["strong", "partial", "missing"] as Verdict[]).map((verdict) => (
              <RequirementGroup
                key={verdict}
                verdict={verdict}
                requirements={grouped[verdict]}
                open={open}
                onToggle={(id) => setOpen((current) => ({ ...current, [id]: !current[id] }))}
              />
            ))}
          </div>
        ) : prepGenerationFailed ? (
          // Checked before `prepGenerating`: a retry of a failed generation
          // sets both at once, and a retry in flight must still read as a
          // recovery from a failure, not as a first attempt.
          <PrepGenerationFailure onRetry={onRetryPrep} retryPending={prepRetryPending} />
        ) : prepGenerating ? (
          <PrepGenerating />
        ) : (
          <PrepPane questions={analysis.prepQuestions} />
        )}
      </div>
    </section>
  );
}

// Same shell as PrepPane's own empty state -- this replaces that state
// rather than sitting beside it, so it should not arrive looking like a
// different kind of surface.
function PrepGenerating() {
  return (
    <div className="availability-state compact">
      <p className="eyebrow">Interview preparation</p>
      <h2>Generating interview questions…</h2>
      <p>The prep service is deriving questions from this posting's finished requirement verdicts. They will appear here when it returns.</p>
    </div>
  );
}

function PrepGenerationFailure({ onRetry, retryPending }: { onRetry?: () => void; retryPending?: boolean }) {
  return (
    <div className="error-state-wrap">
      <article className="error-panel">
        <p className="eyebrow error-eyebrow"><span className="dot verdict-missing" />Interview prep unavailable</p>
        <h2>Question generation failed</h2>
        <p>Career Intelligence could not generate interview questions for this posting. This can be retried without re-running the fit analysis.</p>
        <div className="error-actions">
          <button type="button" className="primary-action" disabled={!onRetry || retryPending} onClick={onRetry}>Retry</button>
        </div>
      </article>
    </div>
  );
}

function AnalysisHeader({
  job,
  requirementCount,
  score,
  requirements,
  tab,
  onTab,
}: {
  job: Extract<AnalysisView, { status: "ready" }>["job"];
  requirementCount: number;
  score: number;
  requirements: RequirementView[];
  tab: "analysis" | "prep";
  onTab: (tab: "analysis" | "prep") => void;
}) {
  const counts = countVerdicts(requirements);
  return (
    <header className="analysis-header">
      <div className="analysis-heading-row">
        <div>
          <h1>{job.title}</h1>
          <p className="job-meta">
            <strong>{job.company}</strong><span>·</span>{job.location && <><span>{job.location}</span><span>·</span></>}{job.posted && <><span>{job.posted}</span><span>·</span></>}
            <span>{requirementCount} requirements extracted</span>
          </p>
        </div>
        <div className="weighted-score"><strong>{Math.round(score * 100)}%</strong><span>Weighted fit</span></div>
      </div>
      <div className="requirement-strip" aria-label="Requirement verdict distribution">
        {requirements.map((item) => <span key={item.id} className={`verdict-${item.verdict}`} />)}
      </div>
      <div className="legend-row">
        {(["strong", "partial", "missing"] as Verdict[]).map((verdict) => (
          <span key={verdict}><span className={`dot verdict-${verdict}`} />{counts[verdict]} {verdict}</span>
        ))}
        <span className="legend-note">Required requirements weighted 2×</span>
      </div>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "analysis"} onClick={() => onTab("analysis")}>Analysis</button>
        <button type="button" role="tab" aria-selected={tab === "prep"} onClick={() => onTab("prep")}>Interview Prep</button>
      </div>
    </header>
  );
}

function RequirementGroup({ verdict, requirements, open, onToggle }: { verdict: Verdict; requirements: RequirementView[]; open: Record<string, boolean>; onToggle: (id: string) => void }) {
  if (requirements.length === 0) return null;
  return (
    <section className="requirement-group">
      <header><span className={`dot verdict-${verdict}`} /><span>{verdict} · {requirements.length}</span><span className="group-rule" /></header>
      {requirements.map((item) => <RequirementRow key={item.id} requirement={item} open={Boolean(open[item.id])} onToggle={() => onToggle(item.id)} />)}
    </section>
  );
}

function ExtractionFailure({ analysis, onRetry, onPaste }: { analysis: Extract<AnalysisView, { status: "extraction-failed" }>; onRetry?: () => void; onPaste?: () => void }) {
  return (
    <section className="analysis-pane">
      <SimpleJobHeader job={analysis.job} suffix="0 requirements extracted" />
      <div className="analysis-scroll error-state-wrap">
        <article className="error-panel">
          <p className="eyebrow error-eyebrow"><span className="dot verdict-missing" />Analysis unavailable</p>
          <h2>Couldn't read the requirements from this posting</h2>
          <p>The posting could not be converted into a reliable requirement list. Career Intelligence will not guess requirements or generate verdicts without source text.</p>
          {(analysis.detail || analysis.sourceUrl) && <div className="technical-detail"><p>{analysis.detail}</p><p>{analysis.sourceUrl}</p></div>}
          <div className="error-actions"><button type="button" className="primary-action" disabled={!onRetry} onClick={onRetry}>Retry extraction</button><button type="button" className="secondary-action" disabled={!onPaste} onClick={onPaste}>Paste posting text instead</button></div>
        </article>
      </div>
    </section>
  );
}

function AnalysisFailure({
  analysis,
  retryPending,
}: {
  analysis: Extract<AnalysisView, { status: "analysis-failed" }>;
  retryPending?: boolean;
}) {
  return (
    <section className="analysis-pane">
      <SimpleJobHeader job={analysis.job} suffix="0 requirements scored" />
      <div className="analysis-scroll error-state-wrap">
        <article className="error-panel">
          <p className="eyebrow error-eyebrow"><span className="dot verdict-missing" />Analysis unavailable</p>
          <h2>The fit analysis for this posting failed</h2>
          <p>Career Intelligence could not score this posting's requirements against your resume. This can be retried without re-extracting the posting.</p>
          <div className="error-actions"><button type="button" className="primary-action" disabled={!analysis.onRetry || retryPending} onClick={analysis.onRetry}>Retry analysis</button></div>
        </article>
      </div>
    </section>
  );
}

function AnalysingState({ analysis }: { analysis: Extract<AnalysisView, { status: "analysing" }> }) {
  return (
    <section className="analysis-pane">
      <SimpleJobHeader job={analysis.job} suffix="Analysis in progress" />
      <div className="analysis-scroll centered-state"><div><p className="eyebrow">Judging requirements</p><h2>Building the fit breakdown</h2><p>{analysis.complete !== undefined && analysis.total ? `${analysis.complete} of ${analysis.total} requirements evaluated.` : "The analysis will appear here when every requirement has a verdict."}</p></div></div>
    </section>
  );
}

function UnavailableState({ analysis }: { analysis: Extract<AnalysisView, { status: "unavailable" }> }) {
  return (
    <section className="analysis-pane">
      <SimpleJobHeader job={analysis.job} suffix="Requirements indexed" />
      <div className="analysis-scroll centered-state"><div className="availability-state"><p className="eyebrow">Fit analysis</p><h2>Analysis service not connected yet</h2><p>This posting is indexed. Its requirement verdicts and cited evidence will appear here when the analysis endpoint is available.</p></div></div>
    </section>
  );
}

function SimpleJobHeader({ job, suffix }: { job: { title: string; company: string }; suffix: string }) {
  return <header className="analysis-header simple-header"><h1>{job.title}</h1><p className="job-meta"><strong>{job.company}</strong><span>·</span><span>{suffix}</span></p><div className="tabs static-tabs"><span>Analysis</span><span aria-disabled="true">Interview Prep</span></div></header>;
}

function countVerdicts(requirements: RequirementView[]): Record<Verdict, number> {
  return requirements.reduce<Record<Verdict, number>>((counts, item) => ({ ...counts, [item.verdict]: counts[item.verdict] + 1 }), { strong: 0, partial: 0, missing: 0 });
}
