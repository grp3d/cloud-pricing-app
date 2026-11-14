/**
 * 023-agent-foundation (FR-001, FR-001a, clarification 4, research R12): the centre column's
 * Canvas and Agent tabs, arranged like the inspector's Pricing and Service tabs: merged with
 * one in front (Canvas by default), or split into an upper and a lower pane with a divider.
 * Tabs move by dragging or from each tab's options menu; the arrangement is saved to the
 * account. Nothing brings Agent forward by itself.
 *
 * - Agent off for everyone, or a guest: the Agent tab is shown but inactive, with the reason
 *   as its tooltip, and the Canvas fills the pane.
 * - When the agent is on but this user can't use it, the Agent tab says why (and, for a
 *   monthly limit, when it resets); it doesn't say what to do.
 *
 * 024 (US6, FR-018): the conversation and a Results pane sit side by side, with a divider whose
 * position is saved to the account; the pane opens when a comparison's result arrives, and on
 * the latest result when a session with results is reopened. A narrow tab stacks them.
 */
import { useQuery } from "@tanstack/react-query";
import { History, MessagesSquare } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useReducer, useState } from "react";

import { api, type AgentResult, type AgentStatus } from "../../api/client";
import {
  CLOSED,
  RESULTS_SPLIT,
  readResultsSplit,
  resultsPane,
  writeResultsSplit,
} from "../../lib/agentResults";
import {
  CANVAS_ONLY,
  CENTER_TABS,
  type CenterAction,
  type CenterTab,
  nextCenter,
  readCenter,
  writeCenter,
} from "../../lib/centerLayout";
import { usePreferences } from "../../lib/preferences";
import { FitTitle } from "../layout/FitTitle";
import { SplitTabPane } from "../layout/SplitTabPane";
import { VerticalSplit } from "../layout/VerticalSplit";
import { Button } from "../ui/button";
import { AgentActivityLog } from "./AgentActivityLog";
import { AgentConversation } from "./AgentConversation";
import { AgentResultsPane } from "./AgentResultsPane";
import { AgentSessionHeader } from "./AgentSessionHeader";
import { refusalText } from "./agentText";

const LABELS: Record<CenterTab, string> = { canvas: "Canvas", agent: "Agent" };

function inactiveReason(status: AgentStatus | undefined): string | null {
  if (status?.enabled) return null;
  if (status?.reason === "guest") return "Log in to use the agent.";
  if (status?.reason === "agent_off") return "The agent is switched off.";
  return "The agent isn't available right now.";
}

export function WorkspaceCenter({
  canvas,
  architectureId,
  title,
}: {
  canvas: ReactNode;
  architectureId: string | null;
  /** The open architecture's name, shown in the upper tab bar (only the upper one when split). */
  title: string | null;
}) {
  const status = useQuery({
    queryKey: ["agentStatus"],
    queryFn: api.getAgentStatus,
    refetchInterval: 60_000,
    retry: false,
  });
  const [prefs] = usePreferences();
  const saved = readCenter(prefs.workspace);
  const reason = inactiveReason(status.data);
  // While the Agent tab is inactive, the saved arrangement is kept but not shown.
  const arrangement = reason ? CANVAS_ONLY : saved;

  const onAction = (action: CenterAction) => {
    if (reason) return;
    const next = nextCenter(saved, action);
    if (next !== saved) writeCenter(next);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-border bg-background">
      <SplitTabPane
        tabs={CENTER_TABS}
        labels={LABELS}
        bodies={{
          canvas: <div className="flex min-h-0 flex-1 flex-col">{canvas}</div>,
          agent:
            status.data && !reason ? (
              <AgentPanel status={status.data} architectureId={architectureId} />
            ) : null,
        }}
        arrangement={arrangement}
        onAction={onAction}
        name="workspace"
        inactive={reason ? { agent: reason } : undefined}
        barCenter={title ? <FitTitle text={title} /> : undefined}
        keepHiddenSized
      />
    </div>
  );
}

function AgentPanel({
  status,
  architectureId,
}: {
  status: AgentStatus;
  architectureId: string | null;
}) {
  const [view, setView] = useState<"conversation" | "activity">("conversation");
  const [prefs] = usePreferences();
  const split = readResultsSplit(prefs.workspace);
  const sessionId = status.session?.id ?? null;
  const detail = useQuery({
    queryKey: ["agentSession"],
    queryFn: api.getAgentSession,
    retry: false,
    enabled: Boolean(sessionId),
  });
  const [streamed, setStreamed] = useState<AgentResult[]>([]);
  const [pane, dispatch] = useReducer(resultsPane, CLOSED);

  // Saved results first, then any that streamed in since the session was last loaded.
  const results = useMemo(() => {
    const saved = detail.data?.results ?? [];
    const seen = new Set(saved.map((r) => r.id));
    return [...saved, ...streamed.filter((r) => !seen.has(r.id))];
  }, [detail.data?.results, streamed]);
  const ids = useMemo(() => results.map((r) => r.id), [results]);
  const byId = useMemo(() => Object.fromEntries(results.map((r) => [r.id, r])), [results]);

  useEffect(() => {
    dispatch({ type: "reset" });
    setStreamed([]);
  }, [sessionId]);
  const savedIds = (detail.data?.results ?? []).map((r) => r.id).join(",");
  useEffect(() => {
    if (detail.data) dispatch({ type: "loaded", ids: savedIds ? savedIds.split(",") : [] });
  }, [savedIds, detail.data]);

  const showPane = view === "conversation" && pane.open && pane.selectedId !== null;
  return (
    <section aria-label="Agent" className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-start gap-2 border-b border-border px-2 py-1.5">
        <h2 className="sr-only">Agent</h2>
        <div role="tablist" aria-label="Agent views" className="flex gap-1 pt-0.5">
          <Button
            type="button"
            size="sm"
            variant={view === "conversation" ? "secondary" : "ghost"}
            role="tab"
            aria-selected={view === "conversation"}
            onClick={() => setView("conversation")}
          >
            <MessagesSquare /> Conversation
          </Button>
          <Button
            type="button"
            size="sm"
            variant={view === "activity" ? "secondary" : "ghost"}
            role="tab"
            aria-selected={view === "activity"}
            onClick={() => setView("activity")}
          >
            <History /> Activity
          </Button>
        </div>
        <div className="ml-auto flex items-start gap-1">
          <AgentSessionHeader session={status.session} />
        </div>
      </header>
      {!status.available && status.reason && (
        <p role="status" className="shrink-0 border-b border-border bg-muted/40 px-2 py-1 text-xs">
          {refusalText(status.reason, status.resets_on ?? null)}
        </p>
      )}
      {status.available && status.on_preview && (
        <p className="shrink-0 border-b border-border px-2 py-1 text-xs text-muted-foreground">
          Free preview: {status.preview_inputs_left}{" "}
          {status.preview_inputs_left === 1 ? "message" : "messages"} left.
        </p>
      )}
      <div className="min-h-0 flex-1">
        {view === "conversation" ? (
          status.session ? (
            <VerticalSplit
              label="Resize conversation and results"
              split={split}
              min={RESULTS_SPLIT.min}
              max={RESULTS_SPLIT.max}
              onCommit={(next) => writeResultsSplit(next)}
              first={
                <AgentConversation
                  architectureId={architectureId}
                  available={status.available}
                  results={{
                    byId,
                    shownId: pane.open ? pane.selectedId : null,
                    onShow: (id) => dispatch({ type: "show", id }),
                    onArrived: (result) => {
                      setStreamed((list) => [...list, result]);
                      dispatch({ type: "arrived", id: result.id });
                    },
                  }}
                />
              }
              second={
                showPane ? (
                  <AgentResultsPane
                    results={results}
                    selectedId={pane.selectedId as string}
                    onStep={(delta) => dispatch({ type: "step", delta, ids })}
                    onClose={() => dispatch({ type: "close" })}
                  />
                ) : null
              }
            />
          ) : (
            <p className="p-3 text-xs text-muted-foreground">
              Start a session with <strong>New agent session</strong> to ask about your
              architectures.
            </p>
          )
        ) : (
          <AgentActivityLog />
        )}
      </div>
    </section>
  );
}
