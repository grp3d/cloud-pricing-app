/**
 * 025 (US3, US4, FR-003–FR-007, FR-015, contracts/proposal-ui.md): one proposal in the Results
 * pane — what will be added, changed and removed, the pricing engine's cost before and after,
 * the assumptions, and Accept / Reject (pending) or Undo / Redo (accepted). The canvas shows only
 * saved work; nothing here is drawn on it (clarification Q1).
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useState } from "react";

import { api, type AgentProposal } from "../../api/client";
import {
  STATUS_TEXT,
  actionErrorText,
  changeText,
  groupItems,
  isStaleRefusal,
  statusOf,
  undoEndedText,
} from "../../lib/agentProposals";
import { DURATION_TEXT, formatMoney, formatPercent } from "../../lib/agentResults";
import { Button } from "../ui/button";

export type AgentProposalViewProps = {
  proposal: AgentProposal;
  /** Where this item sits among the pane's items, for "Item 2 of 3" and ◀ ▶. */
  position: { index: number; total: number };
  onStep: (delta: -1 | 1) => void;
  onClose: () => void;
  /** The architecture open in the workspace (a change can be accepted only on it). */
  openArchitectureId: string | null;
  /** A message is being answered: decisions wait until it's done. */
  answering: boolean;
  /** Open an architecture (after accepting a new one). */
  onOpenArchitecture?: (id: string) => void;
};

function signed(text: string): string {
  return text && !text.startsWith("-") && text !== "$0.00" ? `+${text}` : text;
}

const OP_TITLE = { add: "Added", change: "Changed", remove: "Removed" } as const;

export function AgentProposalView({
  proposal,
  position,
  onStep,
  onClose,
  openArchitectureId,
  answering,
  onOpenArchitecture,
}: AgentProposalViewProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [repriced, setRepriced] = useState(false);
  const status = statusOf(proposal);
  const cost = proposal.cost;
  const isChange = proposal.kind === "change";
  const groups = groupItems(proposal.items);
  const ended = undoEndedText(proposal);
  const notOpen = isChange && proposal.architecture_id !== openArchitectureId;
  const blocked = answering
    ? "Wait until the agent has finished answering."
    : notOpen
      ? `Open ${proposal.architecture_name ?? "the architecture"} to accept this change.`
      : null;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["agentSession"] });
    void queryClient.invalidateQueries({ queryKey: ["agentOperations"] });
    void queryClient.invalidateQueries({ queryKey: ["architecture"] });
    void queryClient.invalidateQueries({ queryKey: ["architectures"] });
  };

  async function run(action: () => Promise<{ open_architecture_id?: string | null }>) {
    setError(null);
    setWorking(true);
    try {
      const out = await action();
      setRepriced(false);
      refresh();
      if (out.open_architecture_id) onOpenArchitecture?.(out.open_architecture_id);
    } catch (e) {
      if (isStaleRefusal(e)) {
        setRepriced(true);
        refresh();
      } else {
        setError(actionErrorText(e));
        refresh();
      }
    } finally {
      setWorking(false);
    }
  }

  const accept = () =>
    run(() => api.acceptProposal(proposal.id, openArchitectureId, repriced));

  return (
    <section aria-label="Proposal" className="flex h-full min-h-0 flex-col text-xs">
      <header className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1">
        <h3 className="sr-only">Proposal</h3>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="Previous result"
          disabled={position.index <= 0}
          onClick={() => onStep(-1)}
        >
          <ChevronLeft />
        </Button>
        <span aria-live="polite">
          Result {position.index + 1} of {position.total}
        </span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="Next result"
          disabled={position.index >= position.total - 1}
          onClick={() => onStep(1)}
        >
          <ChevronRight />
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="Close results"
          className="ml-auto"
          onClick={onClose}
        >
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto px-2 py-1.5">
        <div>
          <p className="font-medium text-foreground">
            {proposal.title}{" "}
            <span className="ml-1 rounded border border-border px-1 py-0.5 text-[10px] font-normal">
              {STATUS_TEXT[status] ?? status}
            </span>
          </p>
          <p className="text-muted-foreground">
            {isChange
              ? proposal.architecture_name
              : proposal.kind === "import"
                ? `Import as ${proposal.architecture_name}`
                : `New architecture: ${proposal.architecture_name}`}
          </p>
          {status === "stale" && !repriced && (
            <p className="text-muted-foreground">
              {proposal.architecture_name} changed after this proposal was made. Accept checks it
              again first.
            </p>
          )}
          {proposal.status === "superseded" && (
            <p className="text-muted-foreground">
              A newer proposal replaced this one; it can&apos;t be accepted.
            </p>
          )}
          {repriced && (
            <p role="status">The figures were updated for the latest version. Check them, then accept.</p>
          )}
        </div>

        {(["add", "change", "remove"] as const).map((op) =>
          groups[op].length ? (
            <div key={op}>
              <p className="font-medium">{OP_TITLE[op]}</p>
              <ul className="list-disc pl-4">
                {groups[op].map((item) => (
                  <li key={item.ref}>
                    {item.label}
                    {op === "change" && changeText(item) && (
                      <span className="block text-muted-foreground">{changeText(item)}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}

        <table className="w-full border-collapse">
          <caption className="sr-only">Cost</caption>
          <thead>
            <tr className="border-y border-border text-left">
              <th scope="col" className="px-1 py-1 font-medium">
                Service
              </th>
              {isChange && (
                <th scope="col" className="px-1 py-1 text-right font-medium">
                  Before
                </th>
              )}
              <th scope="col" className="px-1 py-1 text-right font-medium">
                {isChange ? "After" : "Cost"}
              </th>
              {isChange && (
                <th scope="col" className="px-1 py-1 text-right font-medium">
                  Difference
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {cost.by_service.map((row, i) => (
              <tr key={`${row.label}-${i}`} className="border-b border-border align-top">
                <th scope="row" className="px-1 py-1 text-left font-normal">
                  {row.label}
                </th>
                {isChange && (
                  <td className="px-1 py-1 text-right tabular-nums">{formatMoney(row.before)}</td>
                )}
                <td className="px-1 py-1 text-right tabular-nums">{formatMoney(row.after)}</td>
                {isChange && (
                  <td className="px-1 py-1 text-right tabular-nums">
                    {signed(formatMoney(row.difference))}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-b border-border font-medium">
              <th scope="row" className="px-1 py-1 text-left">
                {cost.after.partial || cost.before?.partial ? "Total (partial)" : "Total"}
              </th>
              {isChange && (
                <td className="px-1 py-1 text-right tabular-nums">
                  {formatMoney(cost.before?.total)}
                </td>
              )}
              <td className="px-1 py-1 text-right tabular-nums">{formatMoney(cost.after.total)}</td>
              {isChange && (
                <td className="px-1 py-1 text-right tabular-nums">
                  {signed(formatMoney(cost.difference))}
                  {cost.percent != null && (
                    <span className="block text-muted-foreground">
                      {formatPercent(cost.percent)}
                    </span>
                  )}
                </td>
              )}
            </tr>
          </tfoot>
        </table>

        <div>
          <p className="font-medium">By region</p>
          <ul className="pl-0">
            {cost.by_region.map((row) => (
              <li key={row.label} className="flex justify-between tabular-nums">
                <span>{row.label}</span>
                <span>
                  {isChange ? `${formatMoney(row.before)} → ` : ""}
                  {formatMoney(row.after)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {cost.contributions.length > 1 && (
          <div>
            <p className="font-medium">Each change&apos;s share, in order</p>
            <ul className="pl-0">
              {cost.contributions.map((c) => (
                <li key={c.group} className="flex justify-between tabular-nums">
                  <span>{c.group}</span>
                  <span>{signed(formatMoney(c.difference))}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {cost.unpriceable.length > 0 && (
          <div>
            <p className="font-medium">Not priced</p>
            <ul className="list-disc pl-4">
              {cost.unpriceable.map((u) => (
                <li key={u.label}>
                  {u.label}: {u.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        {proposal.assumptions.length > 0 && (
          <div>
            <p className="font-medium">Assumptions</p>
            <ul className="list-disc pl-4">
              {proposal.assumptions.map((a) => (
                <li key={a.text}>
                  {a.text}
                  {a.guessed ? " (guess)" : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="text-[10px] text-muted-foreground">
          {DURATION_TEXT[cost.duration] ?? cost.duration} · USD · prices from {String(cost.snapshot.date ?? "")}.
          Nothing is saved until you accept.
        </p>
      </div>

      <footer className="shrink-0 space-y-1 border-t border-border px-2 py-1.5">
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
        {proposal.status === "pending" && (
          <>
            {blocked && <p className="text-muted-foreground">{blocked}</p>}
            <div className="flex gap-1">
              <Button
                type="button"
                size="sm"
                disabled={working || Boolean(blocked)}
                onClick={() => void accept()}
              >
                {repriced ? "Accept updated proposal" : "Accept"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={working || answering}
                onClick={() => void run(() => api.rejectProposal(proposal.id))}
              >
                Reject
              </Button>
            </div>
          </>
        )}
        <UndoControls
          proposal={proposal}
          working={working || answering}
          ended={ended}
          onUndo={() => void run(() => api.undoProposal(proposal.id))}
          onRedo={() => void run(() => api.redoProposal(proposal.id))}
        />
      </footer>
    </section>
  );
}

/** Undo / Redo for an accepted proposal, or why undo has ended (FR-005, FR-006). */
export function UndoControls({
  proposal,
  working,
  ended,
  onUndo,
  onRedo,
}: {
  proposal: AgentProposal;
  working: boolean;
  ended: string | null;
  onUndo: () => void;
  onRedo: () => void;
}) {
  if (proposal.status !== "accepted" || !proposal.undo) return null;
  if (ended) return <p className="text-muted-foreground">{ended}</p>;
  return (
    <div className="flex gap-1">
      {proposal.undo.can_undo && (
        <Button type="button" size="sm" variant="outline" disabled={working} onClick={onUndo}>
          Undo
        </Button>
      )}
      {proposal.undo.can_redo && (
        <Button type="button" size="sm" variant="outline" disabled={working} onClick={onRedo}>
          Redo
        </Button>
      )}
    </div>
  );
}
