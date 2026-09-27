import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type ArchitectureDetail } from "../../src/api/client";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { WorkspacePage } from "../../src/pages/WorkspacePage";

const ARCH_ID = "arch-a";

const architecture = {
  id: ARCH_ID,
  name: "A",
  provider: "aws",
  created_at: "2026-09-26T00:00:00Z",
  is_public: false,
  collections: [],
  connectors: [],
} as unknown as ArchitectureDetail;

// Radix Select (the region dialog) needs these in jsdom.
beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/architectures/${ARCH_ID}`]}>
          <Routes>
            <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Column 1 is the "Cloud Pricing" panel; column 2 is the "Architecture Editor" panel. */
function column1() {
  return screen
    .getByRole("heading", { name: "Cloud Pricing", level: 2, hidden: true })
    .closest("aside") as HTMLElement;
}
function column2() {
  return screen
    .getByRole("heading", { name: "Architecture Editor", level: 2, hidden: true })
    .closest("section") as HTMLElement;
}

describe("WorkspacePage column-scoped errors (016, FR-012)", () => {
  beforeEach(() => {
    vi.spyOn(api, "listProviders").mockResolvedValue([{ code: "aws", name: "AWS", active: true }]);
    vi.spyOn(api, "listRegions").mockResolvedValue({ regions: [{ code: "us-east-1" }] });
    vi.spyOn(api, "listArchitectures").mockResolvedValue([]);
    vi.spyOn(api, "getCurrentUser").mockResolvedValue(
      null as unknown as Awaited<ReturnType<typeof api.getCurrentUser>>,
    );
    vi.spyOn(api, "getArchitecture").mockResolvedValue(architecture);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows an architecture-action error in column 1 only", async () => {
    vi.spyOn(api, "createArchitecture").mockRejectedValue(new Error("Name already taken"));
    renderWorkspace();

    fireEvent.change(await screen.findByLabelText("New Architecture name"), {
      target: { value: "Dup" },
    });
    fireEvent.click(within(column1()).getByRole("button", { name: "Create" }));

    expect(await within(column1()).findByText("Name already taken")).toBeInTheDocument();
    expect(within(column2()).queryByText("Name already taken")).toBeNull();
  });

  it("shows a collection-action error in column 2 only, and dismisses it there only", async () => {
    vi.spyOn(api, "createArchitecture").mockRejectedValue(new Error("Architecture failed"));
    vi.spyOn(api, "createCollection").mockRejectedValue(new Error("Collection failed"));
    renderWorkspace();

    // An architecture error first, so there's one in each column.
    fireEvent.change(await screen.findByLabelText("New Architecture name"), {
      target: { value: "Dup" },
    });
    fireEvent.click(within(column1()).getByRole("button", { name: "Create" }));
    await within(column1()).findByText("Architecture failed");

    fireEvent.change(screen.getByPlaceholderText("Collection name"), {
      target: { value: "Web" },
    });
    fireEvent.click(within(column2()).getByRole("button", { name: /Add/ }));
    const trigger = await screen.findByRole("combobox", { name: "AWS Region" });
    await act(async () => {
      // jsdom has no PointerEvent, so Radix treats this as a touch-style click and opens.
      fireEvent.click(trigger);
    });
    fireEvent.click(await screen.findByRole("option", { name: "us-east-1" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Create" }));

    expect(await within(column2()).findByText("Collection failed")).toBeInTheDocument();
    expect(within(column1()).queryByText("Collection failed")).toBeNull();

    // The region dialog stays open after a failed create (unchanged behavior), which marks the
    // rest of the page aria-hidden — close it before interacting with column 2 again.
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.click(await within(column2()).findByRole("button", { name: "Dismiss" }));
    expect(within(column2()).queryByText("Collection failed")).toBeNull();
    expect(within(column1()).getByText("Architecture failed")).toBeInTheDocument();
  });
});
