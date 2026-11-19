/**
 * 025 (FR-005, FR-015, clarification Q2, contracts/proposal-ui.md): the card under an answer
 * that names its proposal and the cost difference; selecting it shows the proposal in the
 * Results pane. An accepted proposal's card carries Undo / Redo, or why undo has ended.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type AgentProposal } from "../../api/client";
import {
  STATUS_TEXT,
  actionErrorText,
  cardSummary,
  statusOf,
  undoEndedText,
} from "../../lib/agentProposals";
import { UndoControls } from "./AgentProposalView";

export function AgentProposalCard({
  proposal,
  current,
  onShow,
  answering = false,
  onOpenArchitecture,
}: {
  proposal: AgentProposal;
  current: boolean;
  onShow: (id: string) => void;
  answering?: boolean;
  /** Redo of a created or imported architecture opens it again. */
  onOpenArchitecture?: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = statusOf(proposal);

  async function run(action: () => Promise<{ open_architecture_id?: string | null }>) {
    setError(null);
    setWorking(true);
    try {
      const out = await action();
      if (out.open_architecture_id) onOpenArchitecture?.(out.open_architecture_id);
    } catch (e) {
      setError(actionErrorText(e));
    } finally {
      setWorking(false);
      void queryClient.invalidateQueries({ queryKey: ["agentSession"] });
      void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
      void queryClient.invalidateQueries({ queryKey: ["architecture"] });
      void queryClient.invalidateQueries({ queryKey: ["architectures"] });
    }
  }

  return (
    <div
      className={`mt-1 rounded-md border px-2 py-1.5 ${
        current ? "border-primary bg-primary/5" : "border-border bg-background"
      }`}
    >
      <button
        type="button"
        aria-label={`Show proposal: ${proposal.title}`}
        aria-current={current ? "true" : undefined}
        className="focus-ring flex w-full items-start gap-2 rounded text-left hover:bg-muted"
        onClick={() => onShow(proposal.id)}
      >
        <span aria-hidden className="mt-0.5">
          ✎
        </span>
        <span className="min-w-0">
          <span className="block truncate font-medium">
            {proposal.title}{" "}
            <span className="font-normal text-muted-foreground">
              · {STATUS_TEXT[status] ?? status}
            </span>
          </span>
          <span className="block text-muted-foreground">{cardSummary(proposal)}</span>
        </span>
      </button>
      {error && (
        <p role="alert" className="mt-1 text-destructive">
          {error}
        </p>
      )}
      {proposal.status === "accepted" && (
        <div className="mt-1">
          <UndoControls
            proposal={proposal}
            working={working || answering}
            ended={undoEndedText(proposal)}
            onUndo={() => void run(() => api.undoProposal(proposal.id))}
            onRedo={() => void run(() => api.redoProposal(proposal.id))}
          />
        </div>
      )}
    </div>
  );
}
