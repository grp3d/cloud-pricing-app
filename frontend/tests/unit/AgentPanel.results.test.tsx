import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type AgentSessionDetail, type AgentStatus } from "../../src/api/client";
import { WorkspaceCenter } from "../../src/components/agent/AgentPanel";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import * as agentStream from "../../src/lib/agentStream";
import { preferencesStore } from "../../src/lib/preferences";
import { architectureResult } from "./agentResultFixture";

/** 024 US6 (FR-018, FR-019, FR-021): the Results pane in the Agent tab. */

let resize: ((width: number) => void) | null = null;

beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {};
  Element.prototype.setPointerCapture ??= () => {};
  class FakeResizeObserver {
    constructor(private callback: ResizeObserverCallback) {}
    observe() {
      resize = (width) =>
        this.callback(
          [{ contentRect: { width } } as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
    }
    disconnect() {}
    unobserve() {}
  }
  globalThis.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
});

const status: AgentStatus = {
  enabled: true,
  available: true,
  reason: null,
  resets_on: null,
  on_preview: false,
  preview_inputs_left: 0,
  session: { id: "s1", started_at: "2026-11-13T10:00:00Z", closes_at: "2026-11-16T10:00:00Z" },
};

function session(overrides: Partial<AgentSessionDetail> = {}): AgentSessionDetail {
  return {
    id: "s1",
    started_at: "2026-11-13T10:00:00Z",
    closes_at: "2026-11-16T10:00:00Z",
    messages: [],
    results: [],
    ...overrides,
  } as AgentSessionDetail;
}

function renderAgentTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WorkspaceCenter canvas={<p>canvas</p>} architectureId="a1" title="Web app" />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

async function openAgentTab() {
  await screen.findByRole("textbox", { name: "Message the agent" });
  act(() => resize?.(1000));
}

describe("the Agent tab's Results pane", () => {
  beforeEach(() => {
    localStorage.clear();
    // The Agent tab in front (tabs move by pointer; the saved arrangement is the simple way).
    preferencesStore.patchSection("workspace", {
      center: { mode: "merged", upper: "canvas", front: "agent", split: 0.6 },
    });
    vi.spyOn(api, "getAgentStatus").mockResolvedValue(status);
    vi.spyOn(api, "getAgentOperations").mockResolvedValue([]);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows only the conversation while there are no results", async () => {
    vi.spyOn(api, "getAgentSession").mockResolvedValue(session());
    renderAgentTab();
    await openAgentTab();
    expect(screen.queryByRole("region", { name: "Results" })).toBeNull();
    expect(screen.queryByRole("separator", { name: /conversation and results/ })).toBeNull();
  });

  it("opens beside the conversation when a result streams in, with a card", async () => {
    vi.spyOn(api, "getAgentSession").mockResolvedValue(session());
    vi.spyOn(agentStream, "sendAgentMessage").mockImplementation(async (_body, onEvent) => {
      onEvent({ event: "result", result: architectureResult() });
      return { kind: "streamed" };
    });
    renderAgentTab();
    await openAgentTab();
    fireEvent.change(screen.getByRole("textbox", { name: "Message the agent" }), {
      target: { value: "What would this cost on Azure?" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });
    expect(await screen.findByRole("region", { name: "Results" })).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Resize conversation and results" }))
      .toBeInTheDocument();
  });

  it("restores cards and opens on the latest result when the session is reopened", async () => {
    const first = architectureResult({ id: "r1", seq: 1, title: "First" });
    const second = architectureResult({ id: "r2", seq: 2, title: "Second" });
    vi.spyOn(api, "getAgentSession").mockResolvedValue(
      session({
        messages: [
          { id: "u1", role: "user", content: "q", status: "answered", error_kind: null,
            is_preview: false, architecture_id: "a1", created_at: "2026-11-13T10:00:00Z",
            result_ids: [] },
          { id: "g1", role: "agent", content: "Here it is.", status: "complete",
            error_kind: null, is_preview: false, architecture_id: "a1",
            created_at: "2026-11-13T10:00:01Z", result_ids: ["r1", "r2"] },
        ],
        results: [first, second],
      }),
    );
    renderAgentTab();
    await openAgentTab();
    expect(await screen.findByText("Result 2 of 2")).toBeInTheDocument();
    const secondCard = screen.getByRole("button", { name: "Show result: Second" });
    expect(secondCard).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "Show result: First" }));
    expect(screen.getByText("Result 1 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close results" }));
    expect(screen.queryByRole("region", { name: "Results" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show result: Second" }));
    expect(screen.getByText("Result 2 of 2")).toBeInTheDocument();
  });

  it("saves the divider's position to the account", async () => {
    vi.spyOn(api, "getAgentSession").mockResolvedValue(
      session({ results: [architectureResult()] }),
    );
    const patch = vi.spyOn(preferencesStore, "patchSection");
    renderAgentTab();
    await openAgentTab();
    const divider = await screen.findByRole("separator", {
      name: "Resize conversation and results",
    });
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    expect(patch).toHaveBeenCalledWith(
      "workspace",
      expect.objectContaining({ agent_results: { split: 0.5 }, center: expect.anything() }),
    );
  });
});
