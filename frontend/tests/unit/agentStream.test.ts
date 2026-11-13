import { describe, expect, it, vi } from "vitest";

import { parseEventLines, sendAgentMessage } from "../../src/lib/agentStream";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

describe("parseEventLines", () => {
  it("keeps an incomplete line for the next chunk", () => {
    const first = parseEventLines('data: {"event":"status","state":"thinking"}\n\ndata: {"ev');
    expect(first.events).toEqual([{ event: "status", state: "thinking" }]);
    const second = parseEventLines(first.rest + 'ent":"text","delta":"Hi"}\n\n');
    expect(second.events).toEqual([{ event: "text", delta: "Hi" }]);
    expect(second.rest).toBe("");
  });
});

describe("sendAgentMessage", () => {
  it("yields typed events split across chunks and stops at done", async () => {
    const body = streamOf([
      'data: {"event":"accepted","message_id":"m1","is_preview":true,"preview_inputs_left":2}\n',
      '\ndata: {"event":"text","del',
      'ta":"It costs $1.00"}\n\ndata: {"event":"done","agent_message_id":"a1"}\n\n',
      'data: {"event":"text","delta":"ignored"}\n\n',
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(body, { status: 200 })),
    );
    const seen: string[] = [];
    const outcome = await sendAgentMessage({ content: "hi", architecture_id: null }, (e) =>
      seen.push(e.event === "text" ? `text:${e.delta}` : e.event),
    );
    expect(seen).toEqual(["accepted", "text:It costs $1.00", "done"]);
    expect(outcome).toEqual({ kind: "streamed" });
    vi.unstubAllGlobals();
  });

  it("returns a refusal for 423 and busy for 409, without events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ detail: { reason: "user_limit", resets_on: "2026-12-01" } }),
            { status: 423 },
          ),
      ),
    );
    const onEvent = vi.fn();
    expect(await sendAgentMessage({ content: "hi", architecture_id: null }, onEvent)).toEqual({
      kind: "refused",
      reason: "user_limit",
      resetsOn: "2026-12-01",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "busy" }), { status: 409 })),
    );
    expect(await sendAgentMessage({ content: "hi", architecture_id: null }, onEvent)).toEqual({
      kind: "busy",
    });
    expect(onEvent).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("reports a network failure as an error outcome", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("offline"))),
    );
    expect(await sendAgentMessage({ content: "hi", architecture_id: null }, vi.fn())).toEqual({
      kind: "failed",
    });
    vi.unstubAllGlobals();
  });
});
