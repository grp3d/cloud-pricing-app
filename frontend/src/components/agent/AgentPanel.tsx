/**
 * 023-agent-foundation (FR-001, FR-001a, clarifications 1 and 4, research R12): the agent panel
 * in the centre column, under the canvas.
 *
 * - Agent off for everyone, or a guest: no panel at all; the column is exactly as before.
 * - Collapsed (the default): a thin bar under the canvas that opens it.
 * - Open: a movable horizontal bar splits the column between the canvas and the panel (like the
 *   bar between the inspector's Service and Pricing tabs), and the panel's bottom-right corner
 *   sets its own height (like the canvas's corner). The layout is saved to the account.
 * - When the agent is on but this user can't use it, the panel says why (and, for a monthly
 *   limit, when it resets); it doesn't say what to do.
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, ChevronUp, History, MessagesSquare } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";

import { api, type AgentStatus } from "../../api/client";
import {
  type AgentPanelLayout,
  clampPanelHeight,
  clampSplit,
  readAgentPanel,
  splitAfterDrag,
  withAgentPanel,
} from "../../lib/agentPanelLayout";
import { preferencesStore, usePreferences } from "../../lib/preferences";
import { Button } from "../ui/button";
import { AgentActivityLog } from "./AgentActivityLog";
import { AgentConversation } from "./AgentConversation";
import { AgentSessionHeader } from "./AgentSessionHeader";
import { refusalText } from "./agentText";

function saveLayout(layout: AgentPanelLayout) {
  void preferencesStore.patchSection(
    "workspace",
    withAgentPanel(preferencesStore.current.workspace, layout),
  );
}

function dragY(e: React.PointerEvent<HTMLElement>, onMove: (dy: number) => void, onUp: () => void) {
  e.preventDefault();
  const target = e.currentTarget;
  target.setPointerCapture?.(e.pointerId);
  const startY = e.clientY;
  const move = (ev: PointerEvent) => onMove(ev.clientY - startY);
  const up = () => {
    target.removeEventListener("pointermove", move);
    target.removeEventListener("pointerup", up);
    onUp();
  };
  target.addEventListener("pointermove", move);
  target.addEventListener("pointerup", up);
}

export function AgentColumn({
  canvas,
  architectureId,
}: {
  canvas: ReactNode;
  architectureId: string | null;
}) {
  const status = useQuery({
    queryKey: ["agentStatus"],
    queryFn: api.getAgentStatus,
    refetchInterval: 60_000,
    retry: false,
  });
  const [prefs] = usePreferences();
  const layout = readAgentPanel(prefs.workspace);
  const columnRef = useRef<HTMLDivElement>(null);
  const areaRef = useRef<HTMLDivElement>(null);
  const [liveSplit, setLiveSplit] = useState<number | null>(null);
  const [liveHeight, setLiveHeight] = useState<number | null>(null);

  if (!status.data?.enabled) return <>{canvas}</>;

  if (!layout.open) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-1.5">
        <div className="min-h-0 flex-1 overflow-auto">{canvas}</div>
        <button
          type="button"
          className="focus-ring flex shrink-0 items-center gap-2 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs hover:bg-muted"
          onClick={() => saveLayout({ ...layout, open: true })}
          aria-label="Open the agent panel"
        >
          <Bot className="size-3.5" /> Agent
          <ChevronUp className="ml-auto size-3.5" />
        </button>
      </div>
    );
  }

  const split = liveSplit ?? layout.split;
  const height = liveHeight ?? layout.height;

  return (
    <div ref={columnRef} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 overflow-auto" style={{ flexGrow: split, flexBasis: 0 }}>
        {canvas}
      </div>
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize the canvas and the agent panel"
        aria-valuemin={20}
        aria-valuemax={80}
        aria-valuenow={Math.round(split * 100)}
        tabIndex={0}
        className="focus-ring my-1 h-1 shrink-0 cursor-row-resize bg-border transition-colors hover:bg-primary/50 active:bg-primary"
        onPointerDown={(e) => {
          const columnHeight = columnRef.current?.getBoundingClientRect().height ?? 0;
          let latest = layout.split;
          dragY(
            e,
            (dy) => {
              latest = splitAfterDrag(layout.split, dy, columnHeight);
              setLiveSplit(latest);
            },
            () => {
              setLiveSplit(null);
              saveLayout({ ...layout, split: latest });
            },
          );
        }}
        onKeyDown={(e) => {
          const step = e.key === "ArrowUp" ? -0.05 : e.key === "ArrowDown" ? 0.05 : 0;
          if (step === 0) return;
          e.preventDefault();
          saveLayout({
            ...layout,
            split: clampSplit(Math.round((layout.split + step) * 100) / 100),
          });
        }}
      />
      <div
        ref={areaRef}
        className="min-h-0 overflow-auto"
        style={{ flexGrow: 1 - split, flexBasis: 0 }}
      >
        <div
          className="relative flex min-h-0 flex-col rounded-md border border-border bg-card"
          style={{ height: height ?? "100%" }}
        >
          <AgentPanel
            status={status.data}
            architectureId={architectureId}
            onCollapse={() => saveLayout({ ...layout, open: false })}
          />
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize the agent panel height"
            tabIndex={0}
            className="focus-ring absolute right-0 bottom-0 z-10 size-4 cursor-ns-resize touch-none rounded-br hover:bg-primary/20 active:bg-primary/30"
            onPointerDown={(e) => {
              const areaHeight = areaRef.current?.getBoundingClientRect().height ?? 0;
              const start =
                layout.height ?? e.currentTarget.parentElement?.getBoundingClientRect().height ?? 0;
              let latest = start;
              dragY(
                e,
                (dy) => {
                  latest = clampPanelHeight(start + dy, Math.max(areaHeight, start + dy));
                  setLiveHeight(latest);
                },
                () => {
                  setLiveHeight(null);
                  saveLayout({ ...layout, height: Math.round(latest) });
                },
              );
            }}
            onKeyDown={(e) => {
              const step = e.key === "ArrowUp" ? -20 : e.key === "ArrowDown" ? 20 : 0;
              if (step === 0) return;
              e.preventDefault();
              const current =
                layout.height ?? e.currentTarget.parentElement?.getBoundingClientRect().height ?? 0;
              saveLayout({
                ...layout,
                height: Math.round(clampPanelHeight(current + step, current + step)),
              });
            }}
          >
            <svg viewBox="0 0 16 16" className="size-full text-muted-foreground" aria-hidden="true">
              <path
                d="M14 3 L3 14 M14 8 L8 14 M14 13 L13 14"
                stroke="currentColor"
                strokeWidth="1.25"
                strokeLinecap="round"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentPanel({
  status,
  architectureId,
  onCollapse,
}: {
  status: AgentStatus;
  architectureId: string | null;
  onCollapse: () => void;
}) {
  const [view, setView] = useState<"conversation" | "activity">("conversation");
  return (
    <section aria-label="Agent" className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-start gap-2 border-b border-border px-2 py-1.5">
        <h2 className="flex items-center gap-1.5 pt-1 text-xs font-semibold">
          <Bot className="size-3.5" /> Agent
        </h2>
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
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label="Collapse the agent panel"
            onClick={onCollapse}
          >
            <ChevronDown />
          </Button>
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
