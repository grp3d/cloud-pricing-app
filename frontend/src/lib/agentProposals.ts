/**
 * 025-agent-architecture-changes (contracts/proposal-ui.md): the words and figures a proposal
 * shows, shared by its view in the Results pane and its card in the conversation. Figures are
 * the proposal's own (the pricing engine's), rounded like the Results pane (024).
 */
import { ApiStatusError, type AgentProposal } from "../api/client";
import { formatMoney, formatPercent } from "./agentResults";

export const STATUS_TEXT: Record<string, string> = {
  pending: "Pending",
  stale: "Stale",
  accepted: "Accepted",
  undone: "Undone",
  rejected: "Rejected",
  superseded: "Superseded",
  expired: "Expired",
};

/** The badge: "Stale" for a pending proposal whose architecture changed, "Undone" after undo. */
export function statusOf(proposal: AgentProposal): string {
  if (proposal.status === "pending" && proposal.stale) return "stale";
  if (proposal.status === "accepted" && proposal.undo?.status === "undone") return "undone";
  return proposal.status;
}

export const UNDO_ENDED_TEXT: Record<string, string> = {
  edited: "Your latest edit means the agent's previous change can no longer be undone.",
  superseded: "A later change replaced this one, so it can no longer be undone.",
  session_ended: "The session has ended, so this change can no longer be undone.",
  deleted: "The architecture was deleted, so this change can no longer be undone.",
};

export function undoEndedText(proposal: AgentProposal): string | null {
  const undo = proposal.undo;
  if (!undo || undo.status !== "ended" || !undo.end_reason) return null;
  return UNDO_ENDED_TEXT[undo.end_reason] ?? null;
}

function changes(count: number): string {
  return `${count} ${count === 1 ? "change" : "changes"}`;
}

/** "Prod Web · 6 changes · +$722.18 (+45.5%)", or the total for a new architecture. */
export function cardSummary(proposal: AgentProposal): string {
  const name =
    proposal.kind === "change"
      ? (proposal.architecture_name ?? "Architecture")
      : `New: ${proposal.architecture_name ?? proposal.title}`;
  const cost = proposal.cost;
  let money: string;
  if (proposal.kind === "change" && cost.difference != null) {
    const diff = formatMoney(cost.difference);
    const signed = diff.startsWith("-") || diff === "$0.00" ? diff : `+${diff}`;
    money = cost.percent != null ? `${signed} (${formatPercent(cost.percent)})` : signed;
  } else {
    money = formatMoney(cost.after.total);
  }
  return `${name} · ${changes(proposal.items.length)} · ${money}`;
}

export type ItemGroups = Record<"add" | "change" | "remove", AgentProposal["items"]>;

export function groupItems(items: AgentProposal["items"]): ItemGroups {
  const out: ItemGroups = { add: [], change: [], remove: [] };
  for (const item of items) out[item.op].push(item);
  return out;
}

const FIELD_TEXT: Record<string, string> = {
  usage_quantity: "quantity",
  pricing_term: "term",
  purchase_option: "purchase option",
  sku: "product",
  name: "name",
};

/** "quantity 744 → 372; term on demand → reserved 1 year" for a change item. */
export function changeText(item: AgentProposal["items"][number]): string {
  const before = (item.before ?? {}) as Record<string, unknown>;
  const after = (item.after ?? {}) as Record<string, unknown>;
  return Object.keys(after)
    .filter((key) => key in FIELD_TEXT)
    .map((key) => `${FIELD_TEXT[key]} ${String(before[key] ?? "—")} → ${String(after[key])}`)
    .join("; ");
}

/** A refusal's detail as one brief sentence for the view. */
export function actionErrorText(error: unknown): string {
  if (error instanceof ApiStatusError) {
    if (error.detail === "busy") return "Wait until the agent has finished answering.";
    if (typeof error.detail === "string") return error.detail;
  }
  return "That didn't work. Try again.";
}

export function isStaleRefusal(error: unknown): boolean {
  return (
    error instanceof ApiStatusError &&
    error.status === 409 &&
    typeof error.detail === "object" &&
    error.detail !== null &&
    (error.detail as { error?: string }).error === "stale"
  );
}

/** Undo end reasons by proposal id, to notice when one ends while the user watches. */
export type UndoEnds = Record<string, string | null>;

export function undoEnds(proposals: AgentProposal[]): UndoEnds {
  return Object.fromEntries(
    proposals
      .filter((p) => p.status === "accepted" && p.undo)
      .map((p) => [p.id, p.undo?.status === "ended" ? (p.undo.end_reason ?? null) : null]),
  );
}

/** True when a proposal whose undo was still possible has just ended because of an edit. */
export function undoJustEndedByEdit(before: UndoEnds, after: UndoEnds): boolean {
  return Object.entries(after).some(
    ([id, reason]) => reason === "edited" && id in before && before[id] !== "edited",
  );
}

/** 025 (FR-014): the user's own decisions, as the activity log names them. */
export const USER_ACTION_TEXT: Record<string, string> = {
  accept_proposal: "You accepted a proposal",
  reject_proposal: "You rejected a proposal",
  undo_proposal: "You undid a proposal",
  redo_proposal: "You redid a proposal",
};
