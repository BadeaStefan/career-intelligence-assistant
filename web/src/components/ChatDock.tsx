import { useState } from "react";

import type { Citation, ChatScope, MessageSummary } from "../api/types";

interface ChatDockProps {
  jobCompany?: string;
  jobCount: number;
  requirementCount: number;
  connected: boolean;
  forceAllJobs?: boolean;
  excludedJob?: string;
  // Additive (Task 19): real chat behaviour wired in around the shell built
  // in an earlier phase. All optional so the shell still renders inertly
  // (its original, pre-Task-18 behaviour) if a caller passes none of them.
  messages?: MessageSummary[];
  onSend?: (content: string, scope: ChatScope) => void;
  sending?: boolean;
  // Optional notification for a caller that wants to do something *else*
  // with a clicked citation (a resume viewer that scrolls to
  // `char_start`/`char_end`, say). Showing the cited text is not that
  // caller's job: the dock does it itself, below, so a citation chip is
  // never a control that looks clickable and does nothing.
  onCitationClick?: (citation: Citation) => void;
}

export function ChatDock({
  jobCompany,
  jobCount,
  requirementCount,
  connected,
  forceAllJobs = false,
  excludedJob,
  messages = [],
  onSend,
  sending = false,
  onCitationClick,
}: ChatDockProps) {
  // `undefined` means "the user hasn't chosen", not "all jobs". The
  // distinction matters because App.tsx selects the active job in an effect:
  // on the first render after loading finishes, `jobCompany` is still
  // undefined and arrives a render later. A `useState` initialiser reading
  // `jobCompany` would run once, capture "all", and never re-evaluate --
  // leaving the dock scoped to every job while the pane beside it shows one,
  // and sending the user's first question under a scope they never picked.
  // Deriving the default on every render until an explicit choice exists
  // fixes that without letting a later re-render overwrite a real choice.
  const [scope, setScope] = useState<ChatScope | undefined>(undefined);
  const [openCitation, setOpenCitation] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const effectiveScope: ChatScope = forceAllJobs ? "all" : (scope ?? (jobCompany ? "job" : "all"));
  const composerDisabled = !connected || sending;

  const submit = (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || !onSend || composerDisabled) return;
    onSend(trimmed, effectiveScope);
    setDraft("");
  };

  return (
    <aside className="chat-dock">
      <header className="chat-header">
        <div className="chat-title-row"><h2>Ask about this analysis</h2><div className="scope-toggle"><button type="button" className={effectiveScope === "job" ? "active" : ""} disabled={!jobCompany || forceAllJobs} onClick={() => setScope("job")}>This job</button><button type="button" className={effectiveScope === "all" ? "active" : ""} onClick={() => setScope("all")}>All jobs</button></div></div>
        <p>{effectiveScope === "job" && jobCompany ? `Scoped to ${jobCompany} · ${requirementCount} requirements` : `Scoped to ${jobCount} ${jobCount === 1 ? "job" : "jobs"} · ${requirementCount} requirements${excludedJob ? ` · ${excludedJob} excluded` : ""}`}</p>
      </header>
      <div className="chat-transcript">
        {!connected && <div className="chat-notice"><p>Chat will be available when the chat service is connected.</p><p>Scope controls are ready; no sample conversation is shown as real analysis.</p></div>}
        {connected && messages.map((message, index) => (
          <div key={index} className={`chat-message chat-message-${message.role}`}>
            {/* Rendered from `message.scope`, the value persisted on this
                row -- not `effectiveScope`, which is only the *next*
                message's scope. History must never relabel a past turn to
                match wherever the toggle currently sits. */}
            <p className="chat-message-meta">{message.role === "user" ? "You" : "Assistant"} · {message.scope === "job" ? "this job" : "all jobs"}</p>
            <p>{message.content}</p>
            {message.citations.length > 0 && (
              <div className="chat-citations">
                {message.citations.map((citation) => {
                  // Keyed by message *and* handle: "c1" is assigned per
                  // retrieval call, so the same handle recurs across turns
                  // pointing at different chunks.
                  const key = `${index}:${citation.handle}`;
                  const expanded = openCitation === key;
                  return (
                    <button
                      type="button"
                      key={citation.handle}
                      className={expanded ? "chat-citation active" : "chat-citation"}
                      aria-expanded={expanded}
                      onClick={() => {
                        setOpenCitation(expanded ? null : key);
                        onCitationClick?.(citation);
                      }}
                    >
                      [{citation.handle}]
                    </button>
                  );
                })}
              </div>
            )}
            {/* The quote sits under the chips, collapsed until asked for --
                same "show me where this came from" affordance PrepPane uses
                for its evidence, and the same markup, so the two read alike.
                Inlining every quote unconditionally would bury the answer
                the citations belong to. */}
            {message.citations
              .filter((citation) => openCitation === `${index}:${citation.handle}`)
              .map((citation) => (
                <blockquote key={citation.handle} className="citation citation-neutral">
                  <p className="citation-label">Cited from your resume · [{citation.handle}]</p>
                  <p><mark className="highlight-neutral">{citation.text}</mark></p>
                </blockquote>
              ))}
          </div>
        ))}
      </div>
      <footer className="chat-composer">
        <div className="suggestion-chips" aria-hidden={!connected}>{["Where am I weakest here?", "Rewrite my Go bullet", "Compare all jobs", "What should I learn first?"].map((text) => <button type="button" key={text} disabled={composerDisabled} onClick={() => submit(text)}>{text}</button>)}</div>
        <div className="composer-row"><input type="text" disabled={composerDisabled} placeholder="Ask about a requirement, verdict, or citation…" aria-label="Ask about this analysis" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submit(draft); }} /><span>⏎</span></div>
      </footer>
    </aside>
  );
}
