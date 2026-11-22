import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type SystemInfo } from "../../src/api/client";
import { SystemInformationSection } from "../../src/components/admin/SystemInformationSection";

/** 016 (US5), 018 (FR-012, FR-014), 019 (FR-009) and 027 (US4–US6): the Admin page's System
 * Information. 027 US6: app-wide rows at the top, then the Providers and Issues tabs. */

type ProviderInfo = NonNullable<SystemInfo["providers"]>[string];
type Issue = SystemInfo["issues"][number];
type History = NonNullable<ProviderInfo["history"]>;

const ACTIVE: NonNullable<ProviderInfo["active_snapshot"]> = {
  snapshot_date: "2026-09-24",
  revision: 2,
  run_id: "20260924T141210Z-9c41e2",
  pipeline_version: "1.3.0",
  created_at: "2026-09-24T14:19:03Z",
  pinned: false,
  regions: ["eu-west-1", "us-east-1"],
  failed_regions: [],
};

const DONE: History = {
  weeks_built: 52,
  weeks_total: 52,
  gaps: [],
  backfill: "done",
  last_error: null,
  last_built_at: "2026-11-16T03:00:00Z",
};

function provider(name: string, overrides: Partial<ProviderInfo> = {}): ProviderInfo {
  return {
    name,
    status: "current",
    reason: null,
    checked: true,
    active_snapshot: ACTIVE,
    latest_run: { snapshot_date: "2026-09-24", revision: 2, status: "succeeded", failed_regions: [] },
    rejected: null,
    last_check_error: null,
    issues: [],
    history: DONE,
    ...overrides,
  } as ProviderInfo;
}

function info(overrides: Partial<SystemInfo> = {}, aws: Partial<ProviderInfo> = {}): SystemInfo {
  return {
    deployment: { environment: "prod", release: "v1.4.0" },
    source: { kind: "local", location: "/data/pipeline", provider: "aws" },
    // The top-level snapshot fields are AWS's; the page no longer shows them (027 US6).
    active: ACTIVE,
    latest_run: null,
    rejected: null,
    cache: null,
    last_check_at: "2026-09-26T21:05:00Z",
    last_check_error: null,
    check_interval_seconds: 300,
    issues: [],
    providers: { aws: provider("AWS", aws), gcp: provider("GCP") },
    ...overrides,
  } as SystemInfo;
}

function issue(overrides: Partial<Issue>): Issue {
  return {
    provider: "aws",
    kind: "missing_icon",
    snapshot_date: "2026-09-24",
    message: "",
    service_code: null,
    service_name: null,
    is_new: null,
    regions: null,
    count: null,
    ...overrides,
  } as Issue;
}

let search = "";
function LocationProbe() {
  search = useLocation().search;
  return null;
}

function renderSection(props: { pollMs?: number } = {}, path = "/admin?tab=system") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <SystemInformationSection {...props} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The top's app-wide rows: term → value. */
async function topRows(): Promise<Record<string, string>> {
  const list = await screen.findByLabelText("App-wide");
  const rows: Record<string, string> = {};
  for (const term of list.querySelectorAll("dt")) {
    rows[term.textContent ?? ""] = term.nextElementSibling?.textContent ?? "";
  }
  return rows;
}

async function providerRow(name: string): Promise<HTMLElement> {
  const table = await screen.findByRole("table", { name: "Provider snapshots" });
  return within(table).getByText(name, { selector: "td" }).closest("tr") as HTMLElement;
}

async function providerCell(name: string, column: string): Promise<string> {
  const table = await screen.findByRole("table", { name: "Provider snapshots" });
  const header = within(table).getByRole("columnheader", { name: column });
  const index = [...header.parentElement!.children].indexOf(header);
  return (await providerRow(name)).children[index].textContent ?? "";
}

async function openIssues() {
  fireEvent.click(await screen.findByRole("tab", { name: /^Issues/ }));
}

afterEach(() => vi.restoreAllMocks());

describe("the app-wide top (027 US6, FR-017)", () => {
  it("shows the deployment, the source and the last check, and no provider's snapshot", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    const rows = await topRows();
    expect(Object.keys(rows)).toEqual(["Deployment", "Pricing data source", "Last checked"]);
    expect(rows.Deployment).toBe("prod — v1.4.0");
    expect(rows["Pricing data source"]).toBe("local — /data/pipeline");
    expect(screen.getByRole("button", { name: "Check now" })).toBeInTheDocument();
  });

  it("hides the cache for a local source", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    await topRows();
    expect(screen.queryByText("Cache")).not.toBeInTheDocument();
  });

  it("shows every provider's cache entries and how full the shared cache is", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        source: { kind: "s3", location: "s3://cloud-pricing-data-prod", provider: "aws" },
        cache: {
          total_bytes: 268435456,
          max_bytes: 1073741824,
          entries: [
            { provider: "aws", snapshot_date: "2026-09-24", revision: 2, state: "active", bytes: 134217728 },
            { provider: "gcp", snapshot_date: "2026-09-17", revision: 1, state: "cached", bytes: 134217728 },
          ],
        },
      }),
    );
    renderSection();
    expect(await screen.findByText("Cache")).toBeInTheDocument();
    expect(screen.getByText("256 MiB of 1024 MiB (25%)")).toBeInTheDocument();
    expect(screen.getByText("AWS 2026-09-24 r2 — active, 128 MiB")).toBeInTheDocument();
    expect(screen.getByText("GCP 2026-09-17 r1 — cached, 128 MiB")).toBeInTheDocument();
  });

  it("Check now starts a check, then refreshes until the check has run", async () => {
    const first = info();
    const after = info({ last_check_at: "2026-09-26T21:06:00Z" });
    const getInfo = vi
      .spyOn(api, "getSystemInfo")
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(first)
      .mockResolvedValue(after);
    const start = vi.spyOn(api, "startSnapshotCheck").mockResolvedValue({ started: true });
    renderSection({ pollMs: 5 });
    const button = await screen.findByRole("button", { name: "Check now" });
    fireEvent.click(button);
    expect(start).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(button).toBeDisabled());
    await waitFor(() => expect(button).not.toBeDisabled());
    expect(getInfo.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it("Check now shows why it could not start (409)", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    vi.spyOn(api, "startSnapshotCheck").mockRejectedValue(new Error("A check is already running."));
    renderSection();
    fireEvent.click(await screen.findByRole("button", { name: "Check now" }));
    expect(await screen.findByText("A check is already running.")).toBeInTheDocument();
  });
});

describe("the Providers and Issues tabs (027 US6, FR-019)", () => {
  it("opens on Providers, with Issues beside it naming its count", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({ issues: [issue({ service_code: "ZZA" }), issue({ service_code: "ZZB" })] }),
    );
    renderSection();
    const providers = await screen.findByRole("tab", { name: "Providers" });
    expect(providers).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Issues (2)" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("table", { name: "Provider snapshots" })).toBeVisible();
  });

  it("keeps the open tab in the address and moves between tabs from the keyboard", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    await openIssues();
    expect(search).toContain("section=issues");
    expect(search).toContain("tab=system");
    expect(screen.getByText("No issues.")).toBeVisible();
    const issues = screen.getByRole("tab", { name: /^Issues/ });
    fireEvent.keyDown(issues, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Providers" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Providers" })).toHaveFocus();
  });

  it("opens the tab the address names", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection({}, "/admin?tab=system&section=issues");
    expect(await screen.findByRole("tab", { name: /^Issues/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("a provider's row (027 US6, FR-018)", () => {
  it("shows its snapshot with revision, pipeline run and regions", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    expect(await providerCell("AWS", "Active snapshot")).toBe(
      "2026-09-24 r2run 20260924T141210Z-9c41e2, pipeline 1.3.0",
    );
    expect(await providerCell("AWS", "Regions")).toBe("eu-west-1, us-east-1");
  });

  it("shows Pinned when pinned", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({}, { active_snapshot: { ...ACTIVE, pinned: true } }),
    );
    renderSection();
    expect(within(await providerRow("AWS")).getByText("Pinned")).toBeInTheDocument();
  });

  it("says when there is no usable snapshot, and why the last check failed", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({}, { active_snapshot: null, status: "none", last_check_error: "no snapshot available" }),
    );
    renderSection();
    expect(await providerCell("AWS", "Active snapshot")).toBe("None");
    expect(await providerCell("AWS", "Detail")).toContain(
      "last check failed: no snapshot available",
    );
  });

  it("shows the active snapshot's failed regions with their reasons", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({}, {
        active_snapshot: {
          ...ACTIVE,
          failed_regions: [{ region: "sa-east-1", reason: "no data", attempts: 2 }],
        },
      }),
    );
    renderSection();
    expect(await providerCell("AWS", "Detail")).toContain("failed regions: sa-east-1: no data");
  });

  it("shows a partial latest run with its failed regions and reasons", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({}, {
        latest_run: {
          snapshot_date: "2026-10-01",
          revision: 1,
          status: "partial",
          failed_regions: [{ region: "ap-northeast-1", reason: "download timed out", attempts: 3 }],
        },
      }),
    );
    renderSection();
    expect(await providerCell("AWS", "Detail")).toContain(
      "latest run 2026-10-01 r1 partial (ap-northeast-1: download timed out)",
    );
  });

  it("shows the last refused manifest", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({}, { rejected: { snapshot_date: "2026-10-01", revision: 1, reason: "status is partial" } }),
    );
    renderSection();
    expect(await providerCell("AWS", "Detail")).toContain(
      "refused 2026-10-01 r1: status is partial",
    );
  });
});

/** 027 US4 (FR-012, FR-013, data-model §3): each provider's Trends history in its row. */
describe("Trends history (027 US4)", () => {
  it.each<[string, History | null, RegExp]>([
    ["complete", DONE, /^Complete: 52 weeks, last built 2026-11-16$/],
    [
      "missing weeks",
      { ...DONE, weeks_built: 50, gaps: ["2026-09-28", "2026-10-05"] },
      /^2 weeks missing \(50 of 52 built, last built 2026-11-16\)$/,
    ],
    ["building", { ...DONE, weeks_built: 12, backfill: "running" }, /^Building \(12 of 52 weeks\)$/],
    [
      "failed",
      { ...DONE, backfill: "failed", last_error: "S3 access denied" },
      /^Failed: S3 access denied$/,
    ],
    [
      "not started",
      { ...DONE, weeks_built: 0, weeks_total: 0, backfill: "pending", last_built_at: null },
      /^No history yet$/,
    ],
    ["unreadable", null, /^Unavailable$/],
  ])("shows %s", async (_label, history, shown) => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({}, { history }));
    renderSection();
    expect(await providerCell("AWS", "Trends history")).toMatch(shown);
  });

  it("refreshes with the rest of the section", async () => {
    const building = info({}, { history: { ...DONE, weeks_built: 12, backfill: "running" } });
    // The check has run (a new last_check_at), so Check now stops polling.
    const done = info({ last_check_at: "2026-09-26T21:06:00Z" });
    vi.spyOn(api, "getSystemInfo")
      .mockResolvedValueOnce(building)
      .mockResolvedValueOnce(building)
      .mockResolvedValue(done);
    vi.spyOn(api, "startSnapshotCheck").mockResolvedValue({ started: true });
    renderSection({ pollMs: 5 });
    expect(await providerCell("AWS", "Trends history")).toMatch(/^Building/);
    fireEvent.click(await screen.findByRole("button", { name: "Check now" }));
    await waitFor(async () =>
      expect(await providerCell("AWS", "Trends history")).toMatch(/^Complete/),
    );
  });
});

/** 016 (US5) and 027 (US5, FR-014): every provider's issues in one table, in the Issues tab. */
describe("Issues (027 US5)", () => {
  it("lists missing-icon and missing-region issues, marking new services", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        issues: [
          issue({ kind: "missing_regions", message: "lost regions", regions: ["eu-west-2", "us-west-1"] }),
          issue({ message: "no icon", service_code: "ZZNew", service_name: "Brand New Service", is_new: true }),
        ],
      }),
    );
    renderSection();
    await openIssues();
    const table = screen.getByRole("table", { name: "Issues" });
    expect(within(table).getByText("eu-west-2, us-west-1")).toBeInTheDocument();
    const row = within(table).getByText("ZZNew — Brand New Service").closest("tr") as HTMLElement;
    expect(within(row).getByText("New")).toBeInTheDocument();
  });

  it("names each issue's provider and shows the Marketplace count line", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        issues: [
          issue({ service_code: "ZZA", service_name: "A", is_new: false }),
          issue({ provider: "gcp", service_code: "1111-2222-3333", service_name: "Some Service", is_new: true }),
          issue({
            provider: "gcp",
            kind: "marketplace_without_icons",
            snapshot_date: "2026-11-16",
            message: "1,648 Marketplace and third-party GCP services have no icon (not listed).",
            count: 1648,
          }),
        ],
      }),
    );
    renderSection();
    await openIssues();
    const table = screen.getByRole("table", { name: "Issues" });
    expect(within(table).getByRole("columnheader", { name: "Provider" })).toBeInTheDocument();
    const gcpRow = within(table).getByText("1111-2222-3333 — Some Service").closest("tr")!;
    expect(within(gcpRow as HTMLElement).getByText("GCP")).toBeInTheDocument();
    expect(within(gcpRow as HTMLElement).getByText("New")).toBeInTheDocument();
    const awsRow = within(table).getByText("ZZA — A").closest("tr")!;
    expect(within(awsRow as HTMLElement).getByText("AWS")).toBeInTheDocument();
    const summary = within(table)
      .getByText("1,648 Marketplace and third-party GCP services have no icon (not listed).")
      .closest("tr")!;
    expect(within(summary as HTMLElement).getByText("Marketplace, no icon")).toBeInTheDocument();
  });

  it("says so when there are no issues", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    await openIssues();
    expect(screen.getByText("No issues.")).toBeVisible();
  });
});

/** 027 US6 (FR-020): the Issues tab filters by provider and scrolls inside itself. */
describe("Issues filter and scrolling (027 US6)", () => {
  const ISSUES = [
    issue({ service_code: "ZZA", service_name: "A" }),
    issue({ provider: "gcp", service_code: "G1", service_name: "G one" }),
    issue({ provider: "gcp", service_code: "G2", service_name: "G two" }),
    issue({
      provider: "gcp",
      kind: "marketplace_without_icons",
      message: "1,573 Marketplace and third-party GCP services have no icon (not listed).",
      count: 1573,
    }),
  ];

  const filter = () => screen.getByRole("group", { name: "Filter issues by provider" });

  it("offers All and each provider with its count, All first and selected", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({ issues: ISSUES }));
    renderSection();
    await openIssues();
    const buttons = within(filter()).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual([
      "All (4)",
      "AWS (1)",
      "GCP (3)",
      "Azure (0)",
    ]);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("table", { name: "Issues" })).getAllByRole("row")).toHaveLength(5);
  });

  it("shows only the chosen provider's issues and keeps the choice in the address", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({ issues: ISSUES }));
    renderSection();
    await openIssues();
    fireEvent.click(within(filter()).getByRole("button", { name: "GCP (3)" }));
    const table = screen.getByRole("table", { name: "Issues" });
    expect(within(table).queryByText("ZZA — A")).toBeNull();
    expect(within(table).getByText("G1 — G one")).toBeInTheDocument();
    expect(within(table).getByText(/1,573 Marketplace/)).toBeInTheDocument();
    expect(search).toContain("issues=gcp");
    expect(within(filter()).getByRole("button", { name: "GCP (3)" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("says so when the chosen provider has no issues", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({ issues: ISSUES }));
    renderSection({}, "/admin?tab=system&section=issues&issues=azure");
    expect(await screen.findByText("No issues for Azure.")).toBeVisible();
    expect(screen.queryByRole("table", { name: "Issues" })).toBeNull();
  });

  it("scrolls the list inside a focusable region with a header that stays put", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({ issues: ISSUES }));
    renderSection();
    await openIssues();
    const region = screen.getByRole("region", { name: "Issues list" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.className).toMatch(/overflow-y-auto/);
    expect(region.className).toMatch(/max-h-/);
    expect(within(region).getByRole("table", { name: "Issues" }).querySelector("thead")?.className).toMatch(
      /sticky/,
    );
  });
});
