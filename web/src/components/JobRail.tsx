import type { JobRailItem, ResumeRailItem, Verdict } from "../view-models/dashboard";

interface JobRailProps {
  resume: ResumeRailItem | null;
  jobs: JobRailItem[];
  selectedJobId?: string;
  onSelect: (jobId: string) => void;
  onAddJob: () => void;
}

const VERDICTS: Verdict[] = ["strong", "partial", "missing"];

export function JobRail({ resume, jobs, selectedJobId, onSelect, onAddJob }: JobRailProps) {
  return (
    <aside className="job-rail" aria-label="Resume and jobs">
      <section className="resume-block">
        <p className="eyebrow">Resume</p>
        {resume ? (
          <>
            <p className="resume-name">{resume.filename}</p>
            <p className="rail-meta">{resume.detail}</p>
          </>
        ) : (
          <div className="rail-placeholder rail-placeholder-resume" aria-label="No resume" />
        )}
      </section>

      <p className="eyebrow jobs-label">Jobs</p>
      <div className="job-list">
        {jobs.length === 0 && (
          <>
            <div className="rail-placeholder" />
            <div className="rail-placeholder rail-placeholder-faint" />
          </>
        )}
        {jobs.map((job) => {
          const selected = job.id === selectedJobId;
          return (
            <button
              key={job.id}
              type="button"
              className={`job-row job-row-${job.state}${selected ? " is-selected" : ""}`}
              aria-label={`${job.title} at ${job.company}`}
              aria-current={selected ? "true" : undefined}
              onClick={() => onSelect(job.id)}
            >
              <span className="job-line">
                <span className="job-title">{job.title}</span>
                {job.state === "ready" && (
                  <span className={`job-score score-${scoreBand(job.score)}`}>
                    {Math.round(job.score * 100)}%
                  </span>
                )}
                {job.state === "analysing" && <span className="job-score muted">— —</span>}
                {job.state === "failed" && <span className="job-score score-missing">failed</span>}
              </span>
              <span className="job-company">{job.company}</span>
              {job.state === "ready" && <VerdictBar counts={job.verdictCounts} />}
              {job.state === "analysing" && (
                <>
                  <span className="progress-track">
                    <span
                      className="progress-fill"
                      style={{
                        width: `${job.progress ? (job.progress.complete / job.progress.total) * 100 : 0}%`,
                      }}
                    />
                  </span>
                  <span className="progress-label">
                    <span>
                      Analysing
                      {job.progress && ` · judging ${job.progress.complete}/${job.progress.total}`}
                    </span>
                    {job.progress?.secondsRemaining && <span>~{job.progress.secondsRemaining}s</span>}
                  </span>
                </>
              )}
              {job.state === "failed" && (
                <span className="failure-meta">
                  {job.reason === "analysis" ? "Analysis error" : "Extraction error"}
                  {job.failedAt && ` · ${job.failedAt}`}
                </span>
              )}
              {job.state === "unavailable" && <span className="failure-meta neutral">Awaiting analysis service</span>}
            </button>
          );
        })}
      </div>

      <footer className="rail-footer">
        <button type="button" className="text-action" onClick={onAddJob} disabled={!resume}>
          + Add job
        </button>
        <p className="rail-meta">Paste posting text</p>
      </footer>
    </aside>
  );
}

function VerdictBar({ counts }: { counts: Record<Verdict, number> }) {
  return (
    <span className="verdict-bar" aria-label={`${counts.strong} strong, ${counts.partial} partial, ${counts.missing} missing`}>
      {VERDICTS.map((verdict) => (
        <span key={verdict} className={`verdict-segment verdict-${verdict}`} style={{ flex: counts[verdict] }} />
      ))}
    </span>
  );
}

function scoreBand(score: number): Verdict {
  if (score >= 0.8) return "strong";
  if (score >= 0.65) return "partial";
  return "missing";
}
