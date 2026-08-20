import { useState } from "react";

export function TraceDrawer({ connected }: { connected: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="trace-drawer">
      <button type="button" className="trace-trigger" aria-expanded={open} onClick={() => setOpen((value) => !value)}><span>{open ? "▾" : "▸"} How did I get this answer?</span><span>{connected ? "Trace available" : "trace service unavailable"}</span></button>
      {open && <div className="trace-content">{connected ? <p>Trace details</p> : <p>Trace details will appear when the trace service is available.</p>}</div>}
    </section>
  );
}
