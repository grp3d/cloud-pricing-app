import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type ArchitectureDetail } from "../../src/api/client";
import { TopTabs } from "../../src/components/layout/TopTabs";
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
          {/* 021: architecture actions live in the header's architecture menu. */}
          <TopTabs />
          <Routes>
            <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** 021: the header's architecture menu (was Column 1); column 2 is the "Architecture Editor"
 * panel. */
function column1() {
  return screen.getByRole("dialog", { name: "Architectures" });
}
async function createFromMenu(name: string) {
  fireEvent.click(await screen.findByRole("button", { name: "Open architecture menu" }));
  // 021 US6: providers start collapsed; open AWS's panel first.
  fireEvent.click(await screen.findByRole("button", { name: "AWS" }));
  fireEvent.click(await screen.findByRole("button", { name: "New AWS architecture…" }));
  fireEvent.change(screen.getByLabelText("New AWS architecture name"), {
    target: { value: name },
  });
  fireEvent.click(within(column1()).getByRole("button", { name: "Create" }));
}
function column2() {
  return screen
    .getByRole("heading", { name: "Architecture Editor", level: 2, hidden: true })
    .closest("aside") as HTMLElement;
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
    await screen.findByRole("heading", { name: "Architecture Editor", level: 2, hidden: true });

    await createFromMenu("Dup");

    expect(await within(column1()).findByText("Name already taken")).toBeInTheDocument();
    expect(within(column2()).queryByText("Name already taken")).toBeNull();
  });

  it("shows a collection-action error in column 2 only, and dismisses it there only", async () => {
    vi.spyOn(api, "createArchitecture").mockRejectedValue(new Error("Architecture failed"));
    vi.spyOn(api, "createCollection").mockRejectedValue(new Error("Collection failed"));
    renderWorkspace();

    // An architecture error first, so there's one in each place.
    await screen.findByRole("heading", { name: "Architecture Editor", level: 2, hidden: true });
    await createFromMenu("Dup");
    await within(column1()).findByText("Architecture failed");
    // Close the menu (Escape twice: the first clears the name field) before using column 2.
    fireEvent.keyDown(screen.getByLabelText("New AWS architecture name"), { key: "Escape" });
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await vi.waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Architectures" })).toBeNull(),
    );

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

    // The region dialog stays open after a failed create (unchanged behavior), which marks the
    // rest of the page aria-hidden — close it before interacting with column 2 again.
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.click(await within(column2()).findByRole("button", { name: "Dismiss" }));
    expect(within(column2()).queryByText("Collection failed")).toBeNull();
    // The architecture error stayed in the menu: reopening it shows it, and only there.
    fireEvent.click(screen.getByRole("button", { name: "Open architecture menu" }));
    expect(await within(column1()).findByText("Architecture failed")).toBeInTheDocument();
    expect(within(column1()).queryByText("Collection failed")).toBeNull();
  });
});
