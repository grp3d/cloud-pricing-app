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
 */
import { useQuery } from "@tanstack/react-query";
import { History, MessagesSquare } from "lucide-react";
import { type ReactNode, useState } from "react";

import { api, type AgentStatus } from "../../api/client";
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
import { Button } from "../ui/button";
import { AgentActivityLog } from "./AgentActivityLog";
import { AgentConversation } from "./AgentConversation";
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
            <AgentConversation architectureId={architectureId} available={status.available} />
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
