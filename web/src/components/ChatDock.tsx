import { useState } from "react";

interface ChatDockProps {
  jobCompany?: string;
  jobCount: number;
  requirementCount: number;
  connected: boolean;
  forceAllJobs?: boolean;
  excludedJob?: string;
}

export function ChatDock({ jobCompany, jobCount, requirementCount, connected, forceAllJobs = false, excludedJob }: ChatDockProps) {
  const [scope, setScope] = useState<"job" | "all">(jobCompany && !forceAllJobs ? "job" : "all");
  const effectiveScope = forceAllJobs ? "all" : scope;
  return (
    <aside className="chat-dock">
      <header className="chat-header">
        <div className="chat-title-row"><h2>Ask about this analysis</h2><div className="scope-toggle"><button type="button" className={effectiveScope === "job" ? "active" : ""} disabled={!jobCompany || forceAllJobs} onClick={() => setScope("job")}>This job</button><button type="button" className={effectiveScope === "all" ? "active" : ""} onClick={() => setScope("all")}>All jobs</button></div></div>
        <p>{effectiveScope === "job" && jobCompany ? `Scoped to ${jobCompany} · ${requirementCount} requirements` : `Scoped to ${jobCount} ${jobCount === 1 ? "job" : "jobs"} · ${requirementCount} requirements${excludedJob ? ` · ${excludedJob} excluded` : ""}`}</p>
      </header>
      <div className="chat-transcript">
        {!connected && <div className="chat-notice"><p>Chat will be available when the chat service is connected.</p><p>Scope controls are ready; no sample conversation is shown as real analysis.</p></div>}
      </div>
      <footer className="chat-composer">
        <div className="suggestion-chips" aria-hidden={!connected}>{["Where am I weakest here?", "Rewrite my Go bullet", "Compare all jobs", "What should I learn first?"].map((text) => <button type="button" key={text} disabled={!connected}>{text}</button>)}</div>
        <div className="composer-row"><input type="text" disabled={!connected} placeholder="Ask about a requirement, verdict, or citation…" aria-label="Ask about this analysis" /><span>⏎</span></div>
      </footer>
    </aside>
  );
}
