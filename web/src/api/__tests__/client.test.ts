import { afterEach, expect, it, vi } from "vitest";

import { apiClient } from "../client";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("carries the response request id with a chat reply", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ content: "Grounded answer", citations: [] }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "request-42",
        },
      }),
    ),
  );

  const reply = await apiClient.sendChatMessage("session-1", "What is missing?", "job");

  expect(reply.request_id).toBe("request-42");
});

it("encodes the request id when fetching trace details", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ llm_calls: [], retrievals: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  await apiClient.getTrace("request id/42");

  expect(fetchMock).toHaveBeenCalledWith("/api/traces/request%20id%2F42");
});
