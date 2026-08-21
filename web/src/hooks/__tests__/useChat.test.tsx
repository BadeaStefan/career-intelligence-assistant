import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Only the network boundary (`apiClient`) is faked -- matches
// `useAnalysis.test.tsx`'s convention. Real timers throughout: nothing in
// `useChat` polls, so there is no interval to reason about under a fake
// clock.
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    apiClient: {
      createChatSession: vi.fn(),
      sendChatMessage: vi.fn(),
      listChatMessages: vi.fn(),
    },
  };
});

import { apiClient } from "../../api/client";
import type { MessageSummary } from "../../api/types";
import { useChat } from "../useChat";

const mockedCreateSession = vi.mocked(apiClient.createChatSession);
const mockedSendMessage = vi.mocked(apiClient.sendChatMessage);
const mockedListMessages = vi.mocked(apiClient.listChatMessages);

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  // `resetAllMocks`, not `clearAllMocks` -- see useAnalysis.test.tsx for why:
  // a test failing partway through can leave queued `mockResolvedValueOnce`
  // entries that must not leak into the next test.
  vi.resetAllMocks();
});

describe("useChat", () => {
  it("creates a session lazily on the first send, scoped to the given job, then reuses it", async () => {
    mockedCreateSession.mockResolvedValue({ id: "session-1" });
    mockedSendMessage.mockResolvedValue({
      content: "answer",
      citations: [],
      request_id: "request-42",
    });
    mockedListMessages.mockResolvedValue([]);

    const { result } = renderHook(() => useChat("job-1"), { wrapper: createWrapper() });

    result.current.sendMessage.mutate({ content: "hi", scope: "job" });
    await waitFor(() => expect(mockedSendMessage).toHaveBeenCalledTimes(1));

    expect(mockedCreateSession).toHaveBeenCalledTimes(1);
    expect(mockedCreateSession).toHaveBeenCalledWith("job-1");
    expect(mockedSendMessage).toHaveBeenCalledWith("session-1", "hi", "job");
    expect(result.current.requestId).toBe("request-42");

    result.current.sendMessage.mutate({ content: "and now all jobs", scope: "all" });
    await waitFor(() => expect(mockedSendMessage).toHaveBeenCalledTimes(2));

    // Second send reuses the same session -- no second session created.
    expect(mockedCreateSession).toHaveBeenCalledTimes(1);
    expect(mockedSendMessage).toHaveBeenLastCalledWith("session-1", "and now all jobs", "all");
  });

  it("refetches message history after a send so it reflects the persisted scope", async () => {
    mockedCreateSession.mockResolvedValue({ id: "session-1" });
    mockedSendMessage.mockResolvedValue({ content: "answer", citations: [], request_id: "request-1" });
    const persisted: MessageSummary[] = [
      { role: "user", content: "hi", scope: "job", citations: [] },
      { role: "assistant", content: "answer", scope: "job", citations: [] },
    ];
    mockedListMessages.mockResolvedValue(persisted);

    const { result } = renderHook(() => useChat("job-1"), { wrapper: createWrapper() });

    result.current.sendMessage.mutate({ content: "hi", scope: "job" });

    await waitFor(() => expect(result.current.messages).toEqual(persisted));
  });

  it("starts a fresh session when the selected job changes", async () => {
    mockedCreateSession
      .mockResolvedValueOnce({ id: "session-1" })
      .mockResolvedValueOnce({ id: "session-2" });
    mockedSendMessage.mockResolvedValue({ content: "answer", citations: [], request_id: "request-1" });
    mockedListMessages.mockResolvedValue([]);

    const { result, rerender } = renderHook(
      ({ jobDocId }: { jobDocId: string }) => useChat(jobDocId),
      { wrapper: createWrapper(), initialProps: { jobDocId: "job-1" } },
    );

    result.current.sendMessage.mutate({ content: "hi", scope: "job" });
    await waitFor(() => expect(mockedSendMessage).toHaveBeenCalledTimes(1));
    expect(mockedSendMessage).toHaveBeenNthCalledWith(1, "session-1", "hi", "job");

    rerender({ jobDocId: "job-2" });

    result.current.sendMessage.mutate({ content: "hello job 2", scope: "job" });
    await waitFor(() => expect(mockedSendMessage).toHaveBeenCalledTimes(2));

    expect(mockedCreateSession).toHaveBeenCalledTimes(2);
    expect(mockedCreateSession).toHaveBeenLastCalledWith("job-2");
    expect(mockedSendMessage).toHaveBeenNthCalledWith(2, "session-2", "hello job 2", "job");
  });

  it("exposes isPending while a send is in flight", async () => {
    mockedCreateSession.mockResolvedValue({ id: "session-1" });
    let resolveSend: (value: { content: string; citations: never[]; request_id: string }) => void = () => {};
    mockedSendMessage.mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve;
      }),
    );
    mockedListMessages.mockResolvedValue([]);

    const { result } = renderHook(() => useChat("job-1"), { wrapper: createWrapper() });

    result.current.sendMessage.mutate({ content: "hi", scope: "job" });

    await waitFor(() => expect(result.current.sendMessage.isPending).toBe(true));

    resolveSend({ content: "answer", citations: [], request_id: "request-1" });
    await waitFor(() => expect(result.current.sendMessage.isPending).toBe(false));
  });
});
