import type { PrepQuestionView } from "../view-models/dashboard";

export function PrepPane({ questions }: { questions: PrepQuestionView[] }) {
  if (questions.length === 0) {
    return (
      <div className="availability-state compact">
        <p className="eyebrow">Interview preparation</p>
        <h2>Questions will appear after fit analysis</h2>
        <p>The prep service uses the finished requirement verdicts, so it cannot generate grounded questions yet.</p>
      </div>
    );
  }

  return (
    <div className="prep-pane">
      <p className="prep-intro">
        These questions target the claims and gaps most likely to be tested. Each answer frame stays anchored to evidence already found in the resume.
      </p>
      {questions.map((item) => (
        <article key={item.id} className="prep-question">
          <span className="prep-ordinal">{item.ordinal}</span>
          <div className="prep-body">
            <h3>{item.question}</h3>
            <p className="anchor-row">
              <span>Anchored to</span>
              <span className="anchor-chip">{item.requirement}</span>
              <span className={`dot verdict-${item.verdict}`} />
              <span>{item.verdict}</span>
            </p>
            <div className="prep-guidance">
              <section><p className="eyebrow">Why they’ll ask</p><p>{item.why}</p></section>
              <section><p className="eyebrow">How to frame it</p><p>{item.framing}</p></section>
            </div>
            {item.evidence && (
              <blockquote className="citation citation-neutral">
                <p className="citation-label">Answer from · {item.evidence.location}</p>
                <p><mark className="highlight-neutral">{item.evidence.quote}</mark></p>
              </blockquote>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
