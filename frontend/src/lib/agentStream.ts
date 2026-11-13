/**
 * 023-agent-foundation (research R3, contracts/agent-api.md): send a message to the agent and
 * read its answer as server-sent events. `EventSource` can't send the Authorization header, so
 * this reads a `fetch` body stream. Each `data:` line is one typed event (generated types).
 * Refusals arrive as plain JSON before any stream: `423 {reason, resets_on}` and `409 busy`.
 */
import {
  API_BASE,
  apiHeaders,
  type AgentRefusalReason,
  type AgentStreamEvent,
} from "../api/client";

export type SendOutcome =
  | { kind: "streamed" }
  | { kind: "refused"; reason: AgentRefusalReason; resetsOn: string | null }
  | { kind: "busy" }
  | { kind: "no_session" }
  | { kind: "failed" };

/** Splits complete `data:` lines out of `buffer`; the incomplete tail comes back as `rest`. */
export function parseEventLines(buffer: string): { events: AgentStreamEvent[]; rest: string } {
  const lines = buffer.split("\n");
  const rest = lines.pop() ?? "";
  const events: AgentStreamEvent[] = [];
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    try {
      events.push(JSON.parse(line.slice(6)) as AgentStreamEvent);
    } catch {
      // A malformed line is skipped; the stream still ends with done or error.
    }
  }
  return { events, rest };
}

async function stream(
  path: string,
  body: unknown,
  onEvent: (event: AgentStreamEvent) => void,
): Promise<SendOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: apiHeaders(),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { kind: "failed" };
  }
  if (response.status === 423) {
    const detail = (await response.json().catch(() => ({}))).detail ?? {};
    return { kind: "refused", reason: detail.reason, resetsOn: detail.resets_on ?? null };
  }
  if (response.status === 409) return { kind: "busy" };
  if (response.status === 404) return { kind: "no_session" };
  if (!response.ok || !response.body) return { kind: "failed" };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const parsed = parseEventLines(buffer + decoder.decode(value, { stream: true }));
      buffer = parsed.rest;
      for (const event of parsed.events) {
        onEvent(event);
        if (event.event === "done" || event.event === "error") {
          await reader.cancel().catch(() => undefined);
          return { kind: "streamed" };
        }
      }
    }
  } catch {
    return { kind: "failed" };
  }
  return { kind: "streamed" };
}

export function sendAgentMessage(
  body: { content: string; architecture_id: string | null },
  onEvent: (event: AgentStreamEvent) => void,
): Promise<SendOutcome> {
  return stream("/agent/session/messages", body, onEvent);
}

export function retryAgentMessage(
  messageId: string,
  onEvent: (event: AgentStreamEvent) => void,
): Promise<SendOutcome> {
  return stream(`/agent/session/messages/${messageId}/retry`, undefined, onEvent);
}
