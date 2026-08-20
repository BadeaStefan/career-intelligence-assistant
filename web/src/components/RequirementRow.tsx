import type { RequirementView } from "../view-models/dashboard";

interface RequirementRowProps {
  requirement: RequirementView;
  open: boolean;
  onToggle: () => void;
}

export function RequirementRow({ requirement, open, onToggle }: RequirementRowProps) {
  return (
    <article className="requirement-row">
      <button
        type="button"
        className="requirement-trigger"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="requirement-name">{requirement.text}</span>
        <span className="requirement-tag">{requirement.importance}</span>
        <span className={`verdict-badge badge-${requirement.verdict}`}>
          <span className={`dot verdict-${requirement.verdict}`} />
          {requirement.verdict}
        </span>
        <span className="chevron" aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="requirement-detail">
          <p className="rationale">{requirement.rationale}</p>
          {requirement.evidence ? (
            <blockquote className={`citation citation-${requirement.verdict}`}>
              <p className="citation-label">Cited from resume · {requirement.evidence.location}</p>
              <p><mark className={`highlight-${requirement.verdict}`}>{requirement.evidence.quote}</mark></p>
            </blockquote>
          ) : (
            <div className="citation citation-missing citation-empty">
              <p className="citation-label">No evidence found</p>
              <p>{requirement.nearestMiss ?? "No resume span cleared the retrieval threshold."}</p>
            </div>
          )}
          <p className="provenance">
            {requirement.retrievalScore !== undefined &&
              `${requirement.evidence ? "retrieval score" : "best retrieval score"} ${requirement.retrievalScore.toFixed(2)} · `}
            {requirement.evidence ? requirement.gap ?? "1 span cited" : "below 0.45 threshold"}
          </p>
        </div>
      )}
    </article>
  );
}
