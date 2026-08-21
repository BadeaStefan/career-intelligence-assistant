import type { TraceDetail } from "../api/types";

interface TraceDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  requestId?: string;
  trace?: TraceDetail;
  loading?: boolean;
  error?: boolean;
}

export function TraceDrawer({
  open,
  onOpenChange,
  requestId,
  trace,
  loading = false,
  error = false,
}: TraceDrawerProps) {
  const status = trace
    ? `${trace.llm_calls.length} calls · ${trace.retrievals.length} retrievals`
    : loading
      ? "Loading trace…"
      : requestId
        ? "Trace unavailable"
        : "No interaction selected";

  return (
    <section className="trace-drawer">
      <button
        type="button"
        className="trace-trigger"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span>{open ? "▾" : "▸"} How did I get this answer?</span>
        <span>{status}</span>
      </button>
      {open && (
        <div className="trace-content">
          {loading ? (
            <p>Loading trace details…</p>
          ) : error || !trace ? (
            <p>
              {requestId
                ? "Trace details are unavailable for this interaction."
                : "Send a chat message to inspect its trace details."}
            </p>
          ) : (
            <TraceBody trace={trace} />
          )}
        </div>
      )}
    </section>
  );
}

function TraceBody({ trace }: { trace: TraceDetail }) {
  if (trace.llm_calls.length === 0 && trace.retrievals.length === 0) {
    return <p>No telemetry was recorded for this interaction.</p>;
  }

  return (
    <div className="trace-groups">
      {trace.llm_calls.length > 0 && (
        <div className="trace-group">
          <h3>Model calls</h3>
          {trace.llm_calls.map((call) => (
            <article className="trace-call" key={call.id}>
              <div>
                <strong>{call.purpose}</strong>
                <span>{call.model}</span>
                <span className={`trace-status trace-status-${call.status}`}>{call.status}</span>
              </div>
              <div className="trace-metrics">
                <span>{call.prompt_tokens ?? "—"} prompt</span>
                <span>{call.completion_tokens ?? "—"} completion</span>
                <span>{call.latency_ms} ms</span>
                <span>{call.cost_usd === null ? "— cost" : `$${call.cost_usd.toFixed(6)}`}</span>
              </div>
              {call.error_type && <p className="trace-error">{call.error_type}</p>}
            </article>
          ))}
        </div>
      )}
      {trace.retrievals.length > 0 && (
        <div className="trace-group">
          <h3>Retrievals</h3>
          {trace.retrievals.map((retrieval, index) => (
            <article className="trace-retrieval" key={retrieval.id}>
              <p>Retrieval {index + 1} · {retrieval.results.candidates.length} candidates</p>
              <div className="trace-candidates">
                {retrieval.results.candidates.map((candidate) => (
                  <span key={`${retrieval.id}-${candidate.id}`}>
                    <strong>{candidate.handle}</strong> {candidate.score.toFixed(3)}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
