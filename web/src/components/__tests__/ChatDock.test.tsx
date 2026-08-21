import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "../../api/types";
import { ChatDock } from "../ChatDock";

// This suite targets the *real* ChatDock -- built ahead of the backend as a
// presentation shell, with its own toggle/composer markup already in place
// (local `scope` state, two plain `<button>`s, an `<input>`). It does not
// exist to prove wiring the task brief's stale pseudocode (`jobDocId`,
// `role="switch"`) -- that snippet predates this component. See task-19
// brief's "Important divergence" note.

const citation: Citation = {
  handle: "c1",
  document_id: "doc-1",
  chunk_id: "chunk-1",
  char_start: 0,
  char_end: 24,
  text: "Built ingestion pipeline processing 2M events/day",
};

describe("ChatDock", () => {
  it("sends the toggle's current scope with each message, per message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[]}
        onSend={onSend}
      />,
    );

    // Default scope is "job" (a company is selected) -- sent as-is.
    await user.type(screen.getByRole("textbox"), "how do I compare?{Enter}");
    expect(onSend).toHaveBeenNthCalledWith(1, "how do I compare?", "job");

    // Flipping the toggle changes only the *next* message's scope --
    // scope is per message (spec §6), not per session.
    await user.click(screen.getByRole("button", { name: /^all jobs$/i }));
    await user.type(screen.getByRole("textbox"), "which should I apply to?{Enter}");
    expect(onSend).toHaveBeenNthCalledWith(2, "which should I apply to?", "all");
  });

  it("defaults to this-job scope when the selected job arrives a render after mount", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    // App.tsx picks the active job in an effect, so the very first render
    // after loading finishes has no jobCompany yet. A default captured once,
    // at mount, would freeze this dock on "all jobs" while the analysis pane
    // beside it shows a single job -- and the user's first question would go
    // out under a scope they never chose (spec §6: "this job" is default).
    const { rerender } = render(
      <ChatDock jobCount={1} requirementCount={5} connected messages={[]} onSend={onSend} />,
    );
    rerender(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[]}
        onSend={onSend}
      />,
    );

    await user.type(screen.getByRole("textbox"), "where am I weakest?{Enter}");

    expect(onSend).toHaveBeenCalledWith("where am I weakest?", "job");
    expect(screen.getByText(/scoped to acme/i)).toBeInTheDocument();
  });

  it("keeps an explicit all-jobs choice after a job arrives", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <ChatDock
        jobCompany="Acme"
        jobCount={2}
        requirementCount={5}
        connected
        messages={[]}
        onSend={onSend}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^all jobs$/i }));
    // A re-render (a poll landing, a sibling's state change) must not revert
    // a choice the user made -- the job-derived default only applies until
    // there is one.
    rerender(
      <ChatDock
        jobCompany="Globex"
        jobCount={2}
        requirementCount={5}
        connected
        messages={[]}
        onSend={onSend}
      />,
    );

    await user.type(screen.getByRole("textbox"), "compare them{Enter}");
    expect(onSend).toHaveBeenCalledWith("compare them", "all");
  });

  it("reveals the cited text when a citation is clicked", async () => {
    const user = userEvent.setup();
    render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[
          {
            role: "assistant",
            content: "You've shipped production Python [c1].",
            scope: "job",
            citations: [citation],
          },
        ]}
      />,
    );

    // Closed until asked for: a transcript that inlined every quote would
    // bury the answer.
    expect(screen.queryByText(citation.text)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /c1/i }));
    expect(screen.getByText(citation.text)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /c1/i }));
    expect(screen.queryByText(citation.text)).not.toBeInTheDocument();
  });

  it("renders citations as clickable references and fires the click callback", async () => {
    const onCitationClick = vi.fn();
    render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[
          {
            role: "assistant",
            content: "You've shipped production Python [c1].",
            scope: "job",
            citations: [citation],
          },
        ]}
        onCitationClick={onCitationClick}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /c1/i }));
    expect(onCitationClick).toHaveBeenCalledWith(citation);
  });

  it("disables the input while a response is in flight", () => {
    render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[]}
        sending
      />,
    );

    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("does not send while a response is already in flight", async () => {
    const onSend = vi.fn();
    render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[]}
        onSend={onSend}
        sending
      />,
    );

    // A disabled textbox cannot receive typed input at all.
    await userEvent.type(screen.getByRole("textbox"), "anything{Enter}", {
      skipClick: true,
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("renders each history message under the scope stored on its own row, not the current toggle", () => {
    const { container } = render(
      <ChatDock
        jobCompany="Acme"
        jobCount={1}
        requirementCount={5}
        connected
        messages={[
          { role: "user", content: "How do I compare?", scope: "job", citations: [] },
          { role: "assistant", content: "Comparing this job only.", scope: "job", citations: [] },
          { role: "user", content: "What about across jobs?", scope: "all", citations: [] },
          { role: "assistant", content: "Across all jobs...", scope: "all", citations: [] },
        ]}
      />,
    );

    const metas = [...container.querySelectorAll(".chat-message-meta")];
    expect(metas).toHaveLength(4);
    expect(metas[0]?.textContent).toMatch(/this job/i);
    expect(metas[1]?.textContent).toMatch(/this job/i);
    expect(metas[2]?.textContent).toMatch(/all jobs/i);
    expect(metas[3]?.textContent).toMatch(/all jobs/i);
  });
});
