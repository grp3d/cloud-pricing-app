import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  type ArchitectureDetail,
  type ArchitectureSummary,
  type Provider,
  api,
} from "../../src/api/client";
import { TopTabs } from "../../src/components/layout/TopTabs";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { WorkspacePage } from "../../src/pages/WorkspacePage";

/** 021 US1 (FR-001 to FR-007a, contracts/ui.md "Architecture menu"): the header menu that
 * replaces Column 1. It takes over ProviderArchitecturePanel.test.tsx's cases.
 * 021 US6 (FR-041 to FR-043): providers start collapsed and open a panel to the right;
 * architectures can be renamed in place. */

const providers: Provider[] = [
  { code: "azure", name: "Azure", active: true },
  { code: "aws", name: "AWS", active: true },
  { code: "gcp", name: "GCP", active: true },
];

function arch(id: string, name: string, provider: string, isPublic = false): ArchitectureSummary {
  return {
    id,
    name,
    provider,
    created_at: "2026-11-01T00:00:00Z",
    is_public: isPublic,
  } as ArchitectureSummary;
}

const byProvider: Record<string, ArchitectureSummary[]> = {
  aws: [arch("a1", "Web App", "aws", true)],
  gcp: [arch("g1", "Data Lake", "gcp")],
  azure: [],
};

function detail(summary: ArchitectureSummary): ArchitectureDetail {
  return { ...summary, collections: [], connectors: [] } as unknown as ArchitectureDetail;
}

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

let location = "";
function LocationProbe() {
  location = useLocation().pathname;
  return null;
}

function renderHeader(path = "/", { withWorkspace = false } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <TopTabs />
          <LocationProbe />
          <Routes>
            <Route path="/" element={withWorkspace ? <WorkspacePage /> : <p>workspace</p>} />
            <Route
              path="/architectures/:architectureId"
              element={withWorkspace ? <WorkspacePage /> : <p>workspace</p>}
            />
            <Route path="/trends" element={<p>trends</p>} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const menu = () => screen.getByRole("dialog", { name: "Architectures" });

async function openMenu() {
  fireEvent.click(await screen.findByRole("button", { name: "Open architecture menu" }));
  // The provider list renders once the providers arrive.
  await within(menu()).findByRole("button", { name: "AWS" });
  return menu();
}

/** Click a provider in the list and return its panel. */
function showGroup(label: "AWS" | "GCP" | "Azure") {
  fireEvent.click(within(menu()).getByRole("button", { name: label }));
  return within(menu()).getByRole("group", { name: `${label} architectures` });
}

beforeEach(() => {
  vi.spyOn(api, "listProviders").mockResolvedValue(providers);
  vi.spyOn(api, "listArchitectures").mockImplementation(async (p = "aws") => byProvider[p] ?? []);
  vi.spyOn(api, "getCurrentUser").mockResolvedValue({
    id: "u1",
    username: "alice",
    is_admin: false,
  } as unknown as Awaited<ReturnType<typeof api.getCurrentUser>>);
  vi.spyOn(api, "listRegions").mockResolvedValue({ regions: [] });
  vi.spyOn(api, "getArchitecture").mockImplementation(async (id: string) => {
    const found = Object.values(byProvider)
      .flat()
      .find((a) => a.id === id);
    if (!found) throw new Error("not found");
    return detail(found);
  });
  location = "";
});
afterEach(() => vi.restoreAllMocks());

describe("ArchitectureMenu groups", () => {
  it("lists AWS, GCP and Azure collapsed, in that order", async () => {
    renderHeader();
    const m = await openMenu();
    const list = within(m).getByRole("list", { name: "Providers" });
    expect(
      within(list)
        .getAllByRole("button")
        .map((b) => b.getAttribute("aria-label")),
    ).toEqual(["AWS", "GCP", "Azure"]);
    expect(within(m).queryByRole("group")).toBeNull();
    for (const b of within(list).getAllByRole("button")) {
      expect(b).toHaveAttribute("aria-expanded", "false");
    }
  });

  it("shows one provider's architectures beside the list, on click or hover", async () => {
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    expect(await within(aws).findByRole("button", { name: "Web App" })).toBeInTheDocument();
    expect(within(menu()).getByRole("button", { name: "AWS" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    fireEvent.pointerEnter(within(menu()).getByRole("button", { name: "GCP" }));
    const gcp = within(menu()).getByRole("group", { name: "GCP architectures" });
    expect(await within(gcp).findByRole("button", { name: "Data Lake" })).toBeInTheDocument();
    expect(within(menu()).queryByRole("group", { name: "AWS architectures" })).toBeNull();
  });

  it("opens a provider from the keyboard and goes back with ArrowLeft", async () => {
    renderHeader();
    await openMenu();
    const gcpButton = within(menu()).getByRole("button", { name: "GCP" });
    gcpButton.focus();
    fireEvent.keyDown(gcpButton, { key: "ArrowRight" });
    const gcp = within(menu()).getByRole("group", { name: "GCP architectures" });
    const first = await within(gcp).findByRole("button", { name: "Data Lake" });
    await vi.waitFor(() => expect(first).toHaveFocus());
    fireEvent.keyDown(first, { key: "ArrowLeft" });
    expect(gcpButton).toHaveFocus();
  });

  it("gives every group, even an empty one, New and Import", async () => {
    renderHeader();
    await openMenu();
    const azure = showGroup("Azure");
    expect(await within(azure).findByText("No architectures yet.")).toBeInTheDocument();
    expect(within(azure).getByRole("button", { name: "New Azure architecture…" })).toBeEnabled();
    expect(
      within(azure).getByRole("button", { name: "Import an Azure architecture" }),
    ).toBeEnabled();
    expect(
      within(showGroup("AWS")).getByRole("button", { name: "Import an AWS architecture" }),
    ).toBeEnabled();
    expect(
      within(showGroup("GCP")).getByRole("button", { name: "Import a GCP architecture" }),
    ).toBeEnabled();
  });

  it("disables New and Import for an inactive provider and explains why", async () => {
    vi.mocked(api.listProviders).mockResolvedValue([
      ...providers.filter((p) => p.code !== "gcp"),
      { code: "gcp", name: "GCP", active: false, status: "failed", reason: "snapshot rejected" },
    ] as Provider[]);
    renderHeader();
    await openMenu();
    expect(within(menu()).getByRole("button", { name: "GCP" })).toHaveAttribute(
      "title",
      "GCP: snapshot rejected",
    );
    const gcp = showGroup("GCP");
    expect(within(gcp).getByRole("button", { name: "New GCP architecture…" })).toBeDisabled();
    expect(within(gcp).getByRole("button", { name: "Import a GCP architecture" })).toBeDisabled();
    expect(within(gcp).getByText("GCP")).toHaveAttribute("title", "GCP: snapshot rejected");
    // Its existing architectures are still listed and can be opened.
    expect(await within(gcp).findByRole("button", { name: "Data Lake" })).toBeEnabled();
  });

  it("marks the open architecture with aria-current, and the header no longer names it", async () => {
    renderHeader("/architectures/g1");
    await openMenu();
    expect(
      await within(showGroup("GCP")).findByRole("button", { name: "Data Lake" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      await within(showGroup("AWS")).findByRole("button", { name: "Web App" }),
    ).not.toHaveAttribute("aria-current");
    // 021 US5 (FR-036): the name is shown above the canvas instead.
    expect(within(screen.getByRole("banner")).queryByText(/Data Lake/)).toBeNull();
  });

  it("scrolls a long group inside its own list, keeping the other providers reachable", async () => {
    vi.mocked(api.listArchitectures).mockImplementation(async (p = "aws") =>
      p === "aws"
        ? Array.from({ length: 50 }, (_, i) => arch(`x${i}`, `Arch ${i}`, "aws"))
        : (byProvider[p] ?? []),
    );
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    await within(aws).findByRole("button", { name: "Arch 49" });
    const list = within(aws).getByRole("list");
    expect(list.className).toContain("overflow-y-auto");
    expect(list.className).toMatch(/max-h-/);
    // New and Import stay below the list, and the other providers stay in the menu.
    expect(within(aws).getByRole("button", { name: "New AWS architecture…" })).toBeInTheDocument();
    expect(within(menu()).getByRole("button", { name: "Azure" })).toBeInTheDocument();
  });
});

describe("ArchitectureMenu actions", () => {
  it("opens an architecture from another provider and closes the menu", async () => {
    renderHeader("/trends");
    await openMenu();
    fireEvent.click(await within(showGroup("GCP")).findByRole("button", { name: "Data Lake" }));
    expect(location).toBe("/architectures/g1");
    await vi.waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Architectures" })).toBeNull(),
    );
  });

  it("creates in the chosen provider with Enter, then opens it", async () => {
    const create = vi.spyOn(api, "createArchitecture").mockResolvedValue(arch("n1", "Edge", "gcp"));
    renderHeader();
    await openMenu();
    const m = showGroup("GCP");
    fireEvent.click(within(m).getByRole("button", { name: "New GCP architecture…" }));
    const field = within(m).getByLabelText("New GCP architecture name");
    fireEvent.change(field, { target: { value: "  Edge " } });
    fireEvent.submit(field.closest("form")!);
    await vi.waitFor(() => expect(create).toHaveBeenCalledWith("Edge", "gcp"));
    await vi.waitFor(() => expect(location).toBe("/architectures/n1"));
  });

  it("clears the name on the first Escape and keeps the menu open", async () => {
    renderHeader();
    await openMenu();
    const m = showGroup("AWS");
    fireEvent.click(within(m).getByRole("button", { name: "New AWS architecture…" }));
    const field = within(m).getByLabelText("New AWS architecture name");
    fireEvent.change(field, { target: { value: "Draft" } });
    field.focus();
    fireEvent.keyDown(field, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Architectures" })).toBeInTheDocument();
    expect(within(menu()).queryByLabelText("New AWS architecture name")).toBeNull();
    // Reopening the field starts empty.
    fireEvent.click(within(menu()).getByRole("button", { name: "New AWS architecture…" }));
    expect(within(menu()).getByLabelText("New AWS architecture name")).toHaveValue("");
  });

  it("closes on Escape and returns focus to the chevron", async () => {
    renderHeader();
    await openMenu();
    const chevron = screen.getByRole("button", { name: "Open architecture menu" });
    fireEvent.keyDown(menu(), { key: "Escape" });
    await vi.waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Architectures" })).toBeNull(),
    );
    // Radix returns focus after its unmount tick.
    await vi.waitFor(() => expect(chevron).toHaveFocus());
  });

  it("toggles public and private with the existing names", async () => {
    const toggle = vi
      .spyOn(api, "setArchitecturePublic")
      .mockResolvedValue(arch("a1", "Web App", "aws"));
    renderHeader();
    await openMenu();
    fireEvent.click(
      await within(showGroup("AWS")).findByRole("button", { name: "Make Web App private" }),
    );
    await vi.waitFor(() => expect(toggle).toHaveBeenCalledWith("a1", false));
    expect(
      await within(showGroup("GCP")).findByRole("button", { name: "Make Data Lake public" }),
    ).toBeInTheDocument();
  });

  it("deletes only after the confirmation, and leaves the workspace if it was open", async () => {
    const del = vi.spyOn(api, "deleteArchitecture").mockResolvedValue(undefined);
    renderHeader("/architectures/a1");
    await openMenu();
    fireEvent.click(
      await within(showGroup("AWS")).findByRole("button", { name: "Delete Web App" }),
    );
    expect(del).not.toHaveBeenCalled();
    const confirm = await screen.findByRole("button", { name: /^Delete$/ });
    await act(async () => fireEvent.click(confirm));
    await vi.waitFor(() => expect(del).toHaveBeenCalledWith("a1"));
    await vi.waitFor(() => expect(location).toBe("/"));
  });

  it("imports from one provider only", async () => {
    const importable = vi
      .spyOn(api, "listImportableArchitectures")
      .mockResolvedValue({ groups: [] });
    renderHeader();
    await openMenu();
    fireEvent.click(
      within(showGroup("GCP")).getByRole("button", { name: "Import a GCP architecture" }),
    );
    await vi.waitFor(() => expect(importable).toHaveBeenCalledWith("gcp"));
    expect(
      await screen.findByRole("heading", { name: "Import a GCP architecture" }),
    ).toBeInTheDocument();
  });

  it("hides the sharing and Import actions from a guest", async () => {
    vi.mocked(api.getCurrentUser).mockResolvedValue({
      id: "g",
      username: null,
      is_admin: false,
    } as unknown as Awaited<ReturnType<typeof api.getCurrentUser>>);
    renderHeader();
    await openMenu();
    const m = showGroup("AWS");
    await within(m).findByRole("button", { name: "Web App" });
    expect(within(m).queryByRole("button", { name: /^Make Web App/ })).toBeNull();
    expect(within(m).queryByRole("button", { name: /^Import/ })).toBeNull();
    expect(within(m).getByRole("button", { name: "Delete Web App" })).toBeInTheDocument();
  });
});

describe("Renaming an architecture (FR-043)", () => {
  it("puts the edit button between sharing and delete", async () => {
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    await within(aws).findByRole("button", { name: "Web App" });
    const names = within(aws.querySelector("li")!)
      .getAllByRole("button")
      .map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(names).toEqual(["Web App", "Make Web App private", "Rename Web App", "Delete Web App"]);
  });

  it("saves the typed name with Enter", async () => {
    const rename = vi
      .spyOn(api, "renameArchitecture")
      .mockResolvedValue(arch("a1", "Shop Front", "aws"));
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    fireEvent.click(await within(aws).findByRole("button", { name: "Rename Web App" }));
    const field = within(aws).getByLabelText("Name for Web App");
    expect(field).toHaveValue("Web App");
    fireEvent.change(field, { target: { value: " Shop Front " } });
    fireEvent.keyDown(field, { key: "Enter" });
    await vi.waitFor(() => expect(rename).toHaveBeenCalledWith("a1", "Shop Front"));
    await vi.waitFor(() => expect(within(aws).queryByLabelText("Name for Web App")).toBeNull());
  });

  it("cancels with Escape, keeping the menu open and the name unchanged", async () => {
    const rename = vi.spyOn(api, "renameArchitecture");
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    fireEvent.click(await within(aws).findByRole("button", { name: "Rename Web App" }));
    const field = within(aws).getByLabelText("Name for Web App");
    field.focus();
    fireEvent.change(field, { target: { value: "Oops" } });
    fireEvent.keyDown(field, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Architectures" })).toBeInTheDocument();
    expect(within(aws).getByRole("button", { name: "Web App" })).toBeInTheDocument();
    expect(rename).not.toHaveBeenCalled();
  });

  it("doesn't save a blank or unchanged name", async () => {
    const rename = vi.spyOn(api, "renameArchitecture");
    renderHeader();
    await openMenu();
    const aws = showGroup("AWS");
    fireEvent.click(await within(aws).findByRole("button", { name: "Rename Web App" }));
    fireEvent.change(within(aws).getByLabelText("Name for Web App"), { target: { value: "  " } });
    fireEvent.keyDown(within(aws).getByLabelText("Name for Web App"), { key: "Enter" });
    expect(within(aws).queryByLabelText("Name for Web App")).toBeNull();
    expect(rename).not.toHaveBeenCalled();
  });
});

describe("Opening an architecture from the menu (FR-004)", () => {
  it("switches the workspace to that architecture's provider", async () => {
    renderHeader("/", { withWorkspace: true });
    await openMenu();
    fireEvent.click(await within(showGroup("GCP")).findByRole("button", { name: "Data Lake" }));
    // The workspace's regions and catalogue follow the open architecture's provider.
    await vi.waitFor(() => expect(api.listRegions).toHaveBeenCalledWith("gcp"));
    // 021 US5 (FR-036): the name now heads the canvas.
    expect(await screen.findByRole("heading", { name: "GCP · Data Lake" })).toBeInTheDocument();
  });

  it("points a user with nothing open to the menu", async () => {
    renderHeader("/", { withWorkspace: true });
    expect((await screen.findAllByText(/from the Cloud Pricing menu/)).length).toBeGreaterThan(0);
  });
});
