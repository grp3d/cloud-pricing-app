/**
 * 023-agent-foundation (Story 3, FR-010, FR-011): the session's start time and, beneath it,
 * its close time, at the panel's top right; and **New agent session**, which asks to confirm
 * before it deletes the current conversation.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlus } from "lucide-react";
import { useState } from "react";

import { api, type AgentSession } from "../../api/client";
import { Button } from "../ui/button";
import { formatSessionTime } from "./agentText";

export function AgentSessionHeader({ session }: { session: AgentSession | null | undefined }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const start = useMutation({
    mutationFn: (replace: boolean) => api.startAgentSession(replace),
    onSuccess: () => {
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: ["agentStatus"] });
      void queryClient.invalidateQueries({ queryKey: ["agentSession"] });
      void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
    },
  });

  return (
    <div className="flex items-start gap-2">
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => (session ? setConfirming(true) : start.mutate(false))}
        disabled={start.isPending}
      >
        <MessageSquarePlus /> New agent session
      </Button>
      {session && (
        <dl className="text-right text-[11px] leading-tight text-muted-foreground">
          <div>
            <dt className="sr-only">Started</dt>
            <dd>Started {formatSessionTime(session.started_at)}</dd>
          </div>
          <div>
            <dt className="sr-only">Closes</dt>
            <dd>Closes {formatSessionTime(session.closes_at)}</dd>
          </div>
        </dl>
      )}
      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Start a new agent session"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
        >
          <div className="max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg">
            <p className="text-xs">
              Start a new agent session? The current conversation and its activity log will be
              deleted.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConfirming(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                autoFocus
                onClick={() => start.mutate(true)}
                disabled={start.isPending}
              >
                Delete and start new
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
