/**
 * 023-agent-foundation (Stories 1, 2, 4): the conversation. Each message is sent with the
 * architecture open at the time (FR-012); the answer streams in (FR-009) with a status while
 * the agent thinks or looks things up; a failed message offers Retry, which uses no new input.
 *
 * 024 (FR-019): a comparison's result arrives as its own event; its card sits under the answer
 * (or under the question, if the answer failed) and shows the result in the Results pane.
 *
 * 025 (FR-015, FR-017): proposals arrive the same way, with their own cards; when the agent opens
 * one of the user's architectures, the workspace is asked to open it.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type AgentProposal, type AgentResult, type AgentStreamEvent } from "../../api/client";
import { retryAgentMessage, sendAgentMessage, type SendOutcome } from "../../lib/agentStream";
import { Button } from "../ui/button";
import { AgentProposalCard } from "./AgentProposalCard";
import { AgentResultCard } from "./AgentResultCard";
import { ERROR_TEXT, STATUS_TEXT, progressText, refusalText } from "./agentText";

type Live = {
  question: string;
  text: string;
  status: keyof typeof STATUS_TEXT | null;
  progress: { label: string; done: number; total: number } | null;
  resultIds: string[];
  proposalIds: string[];
};

export type ConversationResults = {
  /** Every result known in this session, by id (saved and just streamed). */
  byId: Record<string, AgentResult>;
  shownId: string | null;
  onShow: (id: string) => void;
  onArrived: (result: AgentResult) => void;
  /** 025: proposals by id (saved and just streamed), and the stream's new ones. */
  proposalsById?: Record<string, AgentProposal>;
  onProposal?: (proposal: AgentProposal) => void;
  /** 025: the agent is opening one of the user's architectures. */
  onOpenArchitecture?: (id: string, name: string) => void;
  /** 025: a message is being answered (decisions on proposals wait). */
  onAnswering?: (answering: boolean) => void;
};

export function AgentConversation({
  architectureId,
  available,
  results,
}: {
  architectureId: string | null;
  available: boolean;
  results?: ConversationResults;
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
  const answering = Boolean(live);
  const onAnswering = results?.onAnswering;
  useEffect(() => {
    onAnswering?.(answering);
  }, [answering, onAnswering]);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, live?.text]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["agentSession"] });
    void queryClient.invalidateQueries({ queryKey: ["agentStatus"] });
    void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
  };

  const onEvent = (event: AgentStreamEvent) => {
    if (event.event === "status")
      setLive((l) =>
        l
          ? {
              ...l,
              status: event.state,
              progress:
                event.total != null && event.done != null
                  ? { label: event.label ?? "", done: event.done, total: event.total }
                  : null,
            }
          : l,
      );
    else if (event.event === "result") {
      results?.onArrived(event.result);
      setLive((l) => (l ? { ...l, resultIds: [...l.resultIds, event.result.id] } : l));
    } else if (event.event === "proposal") {
      results?.onProposal?.(event.proposal);
      setLive((l) =>
        l && !l.proposalIds.includes(event.proposal.id)
          ? { ...l, proposalIds: [...l.proposalIds, event.proposal.id] }
          : l,
      );
    } else if (event.event === "open_architecture") {
      results?.onOpenArchitecture?.(event.architecture_id, event.name);
    }
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
    setLive({
      question: content,
      text: "",
      status: "thinking",
      progress: null,
      resultIds: [],
      proposalIds: [],
    });
    finish(await sendAgentMessage({ content, architecture_id: architectureId }, onEvent));
  }

  async function retry(messageId: string, question: string) {
    if (live) return;
    setNotice(null);
    setLive({ question, text: "", status: "thinking", progress: null, resultIds: [], proposalIds: [] });
    finish(await retryAgentMessage(messageId, onEvent));
  }

  if (session.isError) {
    return (
      <p className="p-3 text-xs text-muted-foreground">
        Start a session with <strong>New agent session</strong> to ask about your architectures.
      </p>
    );
  }

  const cards = (ids: string[] | undefined) =>
    results && ids && ids.length > 0
      ? ids
          .map((id) => results.byId[id])
          .filter((r): r is AgentResult => Boolean(r))
          .map((r) => (
            <AgentResultCard
              key={r.id}
              result={r}
              current={results.shownId === r.id}
              onShow={results.onShow}
            />
          ))
      : null;

  const proposalCards = (ids: string[] | undefined) =>
    results?.proposalsById && ids && ids.length > 0
      ? ids
          .map((id) => results.proposalsById?.[id])
          .filter((p): p is AgentProposal => Boolean(p))
          .map((p) => (
            <AgentProposalCard
              key={p.id}
              proposal={p}
              current={results.shownId === p.id}
              onShow={results.onShow}
              answering={answering}
              onOpenArchitecture={(id) => results.onOpenArchitecture?.(id, p.title)}
            />
          ))
      : null;

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
            {cards(m.result_ids)}
            {proposalCards(m.proposal_ids)}
          </li>
        ))}
        {live && (
          <>
            <li className="ml-8 rounded-md bg-primary/10 px-2 py-1.5">{live.question}</li>
            <li className="mr-8 rounded-md bg-muted px-2 py-1.5 whitespace-pre-wrap">
              {live.text}
              {live.status && live.status !== "writing" && (
                <span role="status" className="block text-muted-foreground italic">
                  {live.progress ? progressText(live.progress) : STATUS_TEXT[live.status]}
                </span>
              )}
              {cards(live.resultIds)}
              {proposalCards(live.proposalIds)}
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
