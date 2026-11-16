import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type AgentSessionDetail, type AgentStatus } from "../../src/api/client";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { preferencesStore } from "../../src/lib/preferences";
import { WorkspacePage } from "../../src/pages/WorkspacePage";

/** 025 (US1, quickstart §3 step 1): with no architecture open, the Agent tab is still there, so
 * the agent can propose a new architecture. */

beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {};
  class FakeResizeObserver {
    observe() {}
    disconnect() {}
    unobserve() {}
  }
  globalThis.ResizeObserver ??= FakeResizeObserver as unknown as typeof ResizeObserver;
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

function renderNothingOpen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("the workspace with no architecture open", () => {
  beforeEach(() => {
    localStorage.clear();
    preferencesStore.patchSection("workspace", {
      center: { mode: "merged", upper: "canvas", front: "agent", split: 0.6 },
    });
    vi.spyOn(api, "listProviders").mockResolvedValue([{ code: "aws", name: "AWS", active: true }]);
    vi.spyOn(api, "listRegions").mockResolvedValue({ regions: [{ code: "us-east-1" }] });
    vi.spyOn(api, "listArchitectures").mockResolvedValue([]);
    vi.spyOn(api, "getAgentStatus").mockResolvedValue(status);
    vi.spyOn(api, "getAgentOperations").mockResolvedValue([]);
    vi.spyOn(api, "getAgentSession").mockResolvedValue({
      id: "s1",
      started_at: "2026-11-13T10:00:00Z",
      closes_at: "2026-11-16T10:00:00Z",
      messages: [],
      results: [],
      proposals: [],
    } as unknown as AgentSessionDetail);
  });
  afterEach(() => vi.restoreAllMocks());

  it("offers the Agent tab, and the Canvas tab says to open or create one", async () => {
    renderNothingOpen();
    expect(await screen.findByRole("textbox", { name: "Message the agent" })).toBeInTheDocument();
    expect(screen.getAllByText(/Open or create an architecture/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Architecture Editor" })).toBeNull();
  });

  it("keeps the plain message while the agent is off", async () => {
    vi.spyOn(api, "getAgentStatus").mockResolvedValue({
      ...status,
      enabled: false,
      available: false,
      reason: "disabled",
    } as AgentStatus);
    renderNothingOpen();
    expect((await screen.findAllByText(/Open or create an architecture/)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("textbox", { name: "Message the agent" })).toBeNull();
  });
});
