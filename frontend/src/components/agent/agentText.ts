/** 023-agent-foundation: the panel's fixed wording (clarification 4: refusals say why only). */
import type { AgentRefusalReason } from "../../api/client";

/** "1 December 2026" for the 1st-of-month reset date the server sends ("2026-12-01"). */
export function formatResetDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function refusalText(reason: AgentRefusalReason, resetsOn: string | null): string {
  const resets = resetsOn ? ` It resets on ${formatResetDate(resetsOn)}.` : "";
  switch (reason) {
    case "preview_used":
      return "Your free preview of the agent is used up.";
    case "user_limit":
      return `You've reached your monthly limit for the agent.${resets}`;
    case "global_cap":
      return `The agent has reached its monthly limit.${resets}`;
    case "unavailable":
      return "The agent is unavailable right now.";
    case "agent_off":
      return "The agent is off.";
    case "guest":
      return "The agent is available to named accounts only.";
  }
}

export const ERROR_TEXT: Record<string, string> = {
  timeout: "The agent took too long to answer.",
  unreachable: "The agent's model can't be reached right now.",
  no_credit: "The agent's model account is out of credit. An Admin needs to add credit.",
  key_rejected: "The agent's model rejected its API key. An Admin needs to check the key.",
  rate_limited: "The agent's model is limiting requests. Try again in a minute.",
  bad_output: "The agent's model gave an answer the app couldn't use.",
  too_many_steps: "The agent used all its steps before finishing its answer.",
  failed: "The agent couldn't answer.",
  session_closed: "This session has reached its close time.",
  global_cap: "The agent has reached its monthly limit.",
};

export const STATUS_TEXT = {
  thinking: "Thinking…",
  running_operation: "Looking it up…",
  writing: "Writing…",
} as const;

export function formatSessionTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 024 (research R13): "Matching services (12 of 20)…" while a long operation runs. */
export function progressText(progress: { label: string; done: number; total: number }): string {
  return `${progress.label || "Working"} (${progress.done} of ${progress.total})…`;
}
