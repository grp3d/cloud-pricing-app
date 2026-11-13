/**
 * 023-agent-foundation (Stories 1, 2, 4): the conversation. Each message is sent with the
 * architecture open at the time (FR-012); the answer streams in (FR-009) with a status while
 * the agent thinks or looks things up; a failed message offers Retry, which uses no new input.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type AgentStreamEvent } from "../../api/client";
import { retryAgentMessage, sendAgentMessage, type SendOutcome } from "../../lib/agentStream";
import { Button } from "../ui/button";
import { ERROR_TEXT, STATUS_TEXT, refusalText } from "./agentText";

type Live = {
  question: string;
  text: string;
  status: keyof typeof STATUS_TEXT | null;
};

export function AgentConversation({
  architectureId,
  available,
}: {
  architectureId: string | null;
  available: boolean;
}) {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["agentSession"],
    queryFn: api.getAgentSession,
    retry: false,
  });
  const [draft, setDraft] = useState("");
  const [live, setLive] = useState<Live | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const messages = session.data?.messages ?? [];
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, live?.text]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["agentSession"] });
    void queryClient.invalidateQueries({ queryKey: ["agentStatus"] });
    void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
  };

  const onEvent = (event: AgentStreamEvent) => {
    if (event.event === "status") setLive((l) => (l ? { ...l, status: event.state } : l));
    else if (event.event === "text") setLive((l) => (l ? { ...l, text: l.text + event.delta } : l));
    else if (event.event === "operation")
      void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
  };

  const finish = (outcome: SendOutcome) => {
    setLive(null);
    if (outcome.kind === "refused") setNotice(refusalText(outcome.reason, outcome.resetsOn));
    else if (outcome.kind === "busy") setNotice("The agent is still answering your last message.");
    else if (outcome.kind === "failed") setNotice(ERROR_TEXT.unreachable);
    refresh();
  };

  async function send() {
    const content = draft.trim();
    if (!content || live) return;
    setNotice(null);
    setDraft("");
    setLive({ question: content, text: "", status: "thinking" });
    finish(await sendAgentMessage({ content, architecture_id: architectureId }, onEvent));
  }

  async function retry(messageId: string, question: string) {
    if (live) return;
    setNotice(null);
    setLive({ question, text: "", status: "thinking" });
    finish(await retryAgentMessage(messageId, onEvent));
  }

  if (session.isError) {
    return (
      <p className="p-3 text-xs text-muted-foreground">
        Start a session with <strong>New agent session</strong> to ask about your architectures.
      </p>
    );
  }

  const lastFailed = [...messages].reverse().find((m) => m.role === "user");
  const retryable = lastFailed && lastFailed.status === "failed" ? lastFailed : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2 text-xs" aria-live="polite">
        {messages.map((m) => (
          <li
            key={m.id}
            className={
              m.role === "user"
                ? "ml-8 rounded-md bg-primary/10 px-2 py-1.5"
                : "mr-8 rounded-md bg-muted px-2 py-1.5 whitespace-pre-wrap"
            }
          >
            <span className="sr-only">{m.role === "user" ? "You: " : "Agent: "}</span>
            {m.content}
            {m.role === "user" && m.status === "failed" && (
              <span className="mt-1 block text-destructive">
                {ERROR_TEXT[m.error_kind ?? "failed"] ?? ERROR_TEXT.failed}
              </span>
            )}
          </li>
        ))}
        {live && (
          <>
            <li className="ml-8 rounded-md bg-primary/10 px-2 py-1.5">{live.question}</li>
            <li className="mr-8 rounded-md bg-muted px-2 py-1.5 whitespace-pre-wrap">
              {live.text}
              {live.status && live.status !== "writing" && (
                <span role="status" className="block text-muted-foreground italic">
                  {STATUS_TEXT[live.status]}
                </span>
              )}
            </li>
          </>
        )}
        <div ref={endRef} />
      </ol>
      {notice && (
        <p role="status" className="border-t border-border px-2 py-1 text-xs text-muted-foreground">
          {notice}
        </p>
      )}
      {retryable && !live && (
        <div className="border-t border-border px-2 py-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void retry(retryable.id, retryable.content)}
          >
            <RotateCcw /> Retry
          </Button>
        </div>
      )}
      <form
        className="flex shrink-0 items-end gap-2 border-t border-border p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          aria-label="Message the agent"
          className="focus-ring min-h-9 flex-1 resize-none rounded-md border border-input bg-background px-2 py-1.5 text-xs"
          rows={2}
          maxLength={4000}
          value={draft}
          disabled={!available || Boolean(live)}
          placeholder={architectureId ? "Ask about this architecture…" : "Ask what you can import…"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <Button
          type="submit"
          size="sm"
          disabled={!available || Boolean(live) || !draft.trim()}
          aria-label="Send"
        >
          <Send />
        </Button>
      </form>
    </div>
  );
}
