import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiStatusError,
  api,
  type AgentSessionDetail,
  type AgentStatus,
  type ArchitectureDetail,
} from "../../src/api/client";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { preferencesStore } from "../../src/lib/preferences";
import { WorkspacePage } from "../../src/pages/WorkspacePage";

/** 025 (FR-005): undoing an accepted new architecture removes it. The open copy must not stay on
 * the canvas: the workspace closes it and keeps the Agent tab, where Redo is. */

const ARCH_ID = "arch-new";

const architecture = {
  id: ARCH_ID,
  name: "Three-tier web app",
  provider: "aws",
  created_at: "2026-11-19T00:00:00Z",
  is_public: false,
  collections: [],
  connectors: [],
} as unknown as ArchitectureDetail;

const status: AgentStatus = {
  enabled: true,
  available: true,
  reason: null,
  resets_on: null,
  on_preview: false,
  preview_inputs_left: 0,
  session: { id: "s1", started_at: "2026-11-19T10:00:00Z", closes_at: "2026-11-22T10:00:00Z" },
};

beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {};
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  class FakeResizeObserver {
    observe() {}
    disconnect() {}
    unobserve() {}
  }
  globalThis.ResizeObserver ??= FakeResizeObserver as unknown as typeof ResizeObserver;
});

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/" element={<WorkspacePage />} />
            <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

const gone = () => new ApiStatusError(404, "Architecture not found", "Architecture not found");

describe("an open architecture that goes away", () => {
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
      started_at: "2026-11-19T10:00:00Z",
      closes_at: "2026-11-22T10:00:00Z",
      messages: [],
      results: [],
      proposals: [],
    } as unknown as AgentSessionDetail);
  });
  afterEach(() => vi.restoreAllMocks());

  it("is closed, leaving the empty workspace with the Agent tab", async () => {
    const getArchitecture = vi.spyOn(api, "getArchitecture").mockResolvedValue(architecture);
    const queryClient = renderAt(`/architectures/${ARCH_ID}`);
    expect(
      await screen.findByRole("heading", { name: "Architecture Editor", level: 2, hidden: true }),
    ).toBeInTheDocument();

    getArchitecture.mockRejectedValue(gone());
    await act(() => queryClient.invalidateQueries({ queryKey: ["architecture"] }));

    expect(
      (await screen.findAllByText(/Open or create an architecture/)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Architecture Editor", level: 2, hidden: true }))
      .toBeNull();
    expect(screen.getByRole("textbox", { name: "Message the agent" })).toBeInTheDocument();
  });

  it("still says not found for a link to one that doesn't exist", async () => {
    vi.spyOn(api, "getArchitecture").mockRejectedValue(gone());
    renderAt(`/architectures/${ARCH_ID}`);
    expect((await screen.findAllByText("Architecture not found.")).length).toBeGreaterThan(0);
  });
});
