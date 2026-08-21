import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { TraceDetail } from "../../api/types";
import { TraceDrawer } from "../TraceDrawer";

const trace: TraceDetail = {
  llm_calls: [
    {
      id: "call-1",
      request_id: "request-42",
      purpose: "chat",
      model: "gpt-4o-mini",
      prompt_tokens: 120,
      completion_tokens: 35,
      latency_ms: 245,
      cost_usd: 0.000039,
      status: "succeeded",
      error_type: null,
      created_at: "2026-08-21T12:00:00Z",
    },
  ],
  retrievals: [
    {
      id: "retrieval-1",
      request_id: "request-42",
      results: {
        candidates: [
          { id: "chunk-1", handle: "c1", score: 0.91 },
          { id: "chunk-2", handle: "c2", score: 0.78 },
        ],
      },
      created_at: "2026-08-21T12:00:00Z",
    },
  ],
};

it("renders tokens, latency, cost, and retrieval scores for the interaction", () => {
  render(
    <TraceDrawer
      open
      onOpenChange={() => undefined}
      requestId="request-42"
      trace={trace}
    />,
  );

  expect(screen.getByText(/120 prompt/i)).toBeInTheDocument();
  expect(screen.getByText(/35 completion/i)).toBeInTheDocument();
  expect(screen.getByText(/245 ms/i)).toBeInTheDocument();
  expect(screen.getByText(/\$0\.000039/i)).toBeInTheDocument();
  expect(screen.getByText("c1")).toBeInTheDocument();
  expect(screen.getByText("0.910")).toBeInTheDocument();
});

it("delegates its open state to the parent", async () => {
  const onOpenChange = vi.fn();
  render(
    <TraceDrawer
      open={false}
      onOpenChange={onOpenChange}
      requestId="request-42"
      trace={trace}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: /how did i get this answer/i }));
  expect(onOpenChange).toHaveBeenCalledWith(true);
});
