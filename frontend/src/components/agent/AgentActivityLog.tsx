/**
 * 023-agent-foundation (Story 7, FR-024, constitution Principle VII): every operation the agent
 * ran in this session, with its inputs, outcome, time and the pricing snapshot behind any
 * figure.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { formatSessionTime } from "./agentText";

function snapshotText(snapshot: Record<string, unknown> | null | undefined): string | null {
  if (!snapshot) return null;
  return Object.entries(snapshot)
    .map(([provider, value]) => {
      const s = value as { date?: string; revision?: number };
      return `${provider.toUpperCase()} ${s.date ?? "?"} r${s.revision ?? "?"}`;
    })
    .join(", ");
}

export function AgentActivityLog() {
  const log = useQuery({
    queryKey: ["agentOperations"],
    queryFn: api.getAgentOperations,
    retry: false,
  });
  const operations = log.data ?? [];
  if (operations.length === 0) {
    return <p className="p-3 text-xs text-muted-foreground">The agent hasn't run anything yet.</p>;
  }
  return (
    <ol className="h-full space-y-1.5 overflow-y-auto p-2 text-xs" aria-label="Agent activity log">
      {operations.map((op, index) => {
        const snapshot = snapshotText(op.snapshot as Record<string, unknown> | null);
        return (
          <li
            key={`${op.message_id}-${index}`}
            className="rounded-md border border-border px-2 py-1.5"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-medium">{op.name}</span>
              <span className={op.outcome === "ok" ? "text-muted-foreground" : "text-destructive"}>
                {op.outcome === "ok" ? "ok" : "failed"} · {formatSessionTime(op.started_at)} ·{" "}
                {op.duration_ms} ms
              </span>
            </div>
            {Object.keys(op.inputs).length > 0 && (
              <div className="text-muted-foreground">Inputs: {JSON.stringify(op.inputs)}</div>
            )}
            <div className="text-muted-foreground">Result: {JSON.stringify(op.summary)}</div>
            {snapshot && <div className="text-muted-foreground">Pricing snapshot: {snapshot}</div>}
          </li>
        );
      })}
    </ol>
  );
}
