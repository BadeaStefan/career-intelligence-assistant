import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { ChatScope } from "../api/types";

const CHAT_KEY = ["chat"] as const;

function messagesKey(sessionId: string | undefined) {
  return [...CHAT_KEY, sessionId ?? "none", "messages"] as const;
}

/**
 * One chat session binds to whichever job the dock is currently open on
 * (spec §6): the session is created lazily, on the first send, from
 * whatever `jobDocId` this hook was called with at that moment. `scope`
 * itself travels per message instead -- supplied fresh on every
 * `sendMessage.mutate({ content, scope })` call by the caller (`ChatDock`'s
 * own toggle state), never inferred or cached here.
 *
 * A session's job binding is set once at creation and never changes
 * server-side (`ChatService.send` reads `session.job_doc_id` for
 * `scope: "job"` requests -- see `chat/service.py`), so switching to a
 * different job resets `sessionId`: a session still bound to the previous
 * job would otherwise keep answering "this job" questions about the wrong
 * job. This mirrors `App.tsx`'s own `useEffect`-driven reset of
 * `selectedJobId`.
 */
export function useChat(jobDocId: string | undefined) {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string>();

  useEffect(() => {
    setSessionId(undefined);
  }, [jobDocId]);

  const query = useQuery({
    queryKey: messagesKey(sessionId),
    queryFn: () => apiClient.listChatMessages(sessionId as string),
    enabled: Boolean(sessionId),
  });

  const sendMessage = useMutation({
    mutationFn: async ({ content, scope }: { content: string; scope: ChatScope }) => {
      const activeSessionId = sessionId ?? (await apiClient.createChatSession(jobDocId)).id;
      await apiClient.sendChatMessage(activeSessionId, content, scope);
      return activeSessionId;
    },
    onSuccess: (activeSessionId) => {
      setSessionId(activeSessionId);
      // History is re-fetched from the server rather than appended locally
      // from the send response (which only carries the assistant's reply,
      // not the user's own message) -- the transcript must always render
      // the scope actually persisted on each row, never a value assumed
      // client-side.
      queryClient.invalidateQueries({ queryKey: messagesKey(activeSessionId) });
    },
  });

  return {
    messages: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    sendMessage,
  };
}
