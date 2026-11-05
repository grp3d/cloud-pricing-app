import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Movers, Provider } from "../../src/api/client";
import { MoversPanel } from "../../src/components/trends/MoversPanel";
import {
  formatChangePct,
  moversNeedCleaning,
  moversNote,
  resolveMoversSelection,
} from "../../src/lib/trends";

const provider = (code: "aws" | "gcp" | "azure", active: boolean): Provider => ({
  code,
  name: code.toUpperCase(),
  active,
  status: active ? "current" : "failed",
  reason: active ? null : "x",
  snapshot_date: active ? "2026-10-12" : null,
  snapshot_revision: active ? 1 : null,
});
const providers = [provider("aws", true), provider("gcp", true), provider("azure", false)];
const regions = {
  aws: [
    { code: "us-east-1", display_name: "us-east-1" },
    { code: "us-west-2", display_name: "us-west-2" },
  ],
  gcp: [{ code: "us-east1", display_name: "us-east1" }],
};

const base: Movers = {
  provider: "aws",
  category: "all",
  regions: [],
  period_weeks: 52,
  status: "ok",
  reason: null,
  from_snapshot: "2026-09-07 r1",
  to_snapshot: "2026-10-12 r1",
  weeks_available: 5,
  increases: [
    {
      service_name: "Amazon EC2",
      description: "m7i.large Linux On Demand",
      region: "us-east-1",
      unit: "Hrs",
      start_price: "0.1",
      end_price: "0.11",
      change_pct: 10,
      tier_note: null,
    },
  ],
  decreases: [
    {
      service_name: "AWS Data Transfer",
      description: "Internet egress",
      region: "us-east-1",
      unit: "GB",
      start_price: "0.09",
      end_price: "0.085",
      change_pct: -5.56,
      tier_note: "Compared on the first non-zero tier",
    },
  ],
  message: null,
};

const getTrendMovers = vi.fn();
const patchSection = vi.fn();

vi.mock("../../src/lib/preferences", () => ({
  usePreferences: () => [
    {
      migrated_from_browser: true,
      trends: {
        charts: { providers: [{ provider: "aws", regions: [] }], category: "all" },
        movers: { provider: "gcp", category: "storage", regions: ["us-east1"], period_weeks: 4 },
      },
    },
    patchSection,
    true,
  ],
}));

vi.mock("../../src/api/client", async (original) => {
  const actual = await original<typeof import("../../src/api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listProviders: vi.fn(async () => providers),
      listRegions: vi.fn(async (code: "aws" | "gcp") => ({ regions: regions[code] })),
      getTrendSeries: vi.fn(async () => ({ metric: "skus_changed", category: "all", series: [] })),
      getTrendMovers: (...args: unknown[]) => getTrendMovers(...args),
    },
  };
});

function renderPanel(onChange = vi.fn(), onReset = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MoversPanel
        providers={providers.filter((p) => p.active)}
        regionsByProvider={regions}
        selection={{ provider: "aws", category: "all", regions: [], period_weeks: 52 }}
        onChange={onChange}
        onReset={onReset}
      />
    </QueryClientProvider>,
  );
  return { onChange, onReset };
}

describe("MoversPanel (019, US3, FR-016 to FR-019)", () => {
  beforeEach(() => {
    getTrendMovers.mockReset();
    patchSection.mockClear();
  });

  it("lists increases and decreases with every published field", async () => {
    getTrendMovers.mockResolvedValue(base);
    renderPanel();
    const ups = await screen.findByRole("region", { name: "Largest increases" });
    expect(within(ups).getByText("Amazon EC2")).toBeInTheDocument();
    expect(within(ups).getByText(/m7i\.large Linux On Demand/)).toBeInTheDocument();
    expect(within(ups).getByText("+10.00%")).toBeInTheDocument();
    expect(within(ups).getByText(/us-east-1/)).toHaveTextContent("$0.1 → $0.11 per Hrs");
    const downs = screen.getByRole("region", { name: "Largest decreases" });
    expect(within(downs).getByText("−5.56%")).toBeInTheDocument();
    expect(within(downs).getByText("Compared on the first non-zero tier")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Compares 2026-09-07 r1 with 2026-10-12 r1 (only 5 weeks of history so far).",
      ),
    ).toBeInTheDocument();
    expect(getTrendMovers).toHaveBeenCalledWith({
      provider: "aws",
      category: "all",
      regions: [],
      period_weeks: 52,
    });
  });

  it("shows the empty message when nothing changed", async () => {
    getTrendMovers.mockResolvedValue({
      ...base,
      increases: [],
      decreases: [],
      message: "No price changes in this period",
    });
    renderPanel();
    expect(await screen.findByText("No price changes in this period")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Largest increases" })).toBeNull();
  });

  it("reports selector changes; a new provider starts with all regions", async () => {
    getTrendMovers.mockResolvedValue(base);
    const { onChange } = renderPanel();
    fireEvent.click(screen.getByRole("checkbox", { name: "us-west-2" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ provider: "aws", regions: ["us-west-2"] }),
    );
    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "13" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ period_weeks: 13 }));
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "gcp" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ provider: "gcp", regions: [] }),
    );
  });
});

describe("movers selection helpers (019, FR-016, FR-020)", () => {
  it("defaults to the first available provider, all categories, all regions, 52 weeks", () => {
    expect(resolveMoversSelection(null, providers, {})).toEqual({
      provider: "aws",
      category: "all",
      regions: [],
      period_weeks: 52,
    });
    expect(resolveMoversSelection(null, [provider("aws", false)], {})).toBeNull();
  });

  it("drops a provider or region that is no longer available", () => {
    const stale = {
      provider: "azure" as const,
      category: "compute" as const,
      regions: ["x"],
      period_weeks: 4 as const,
    };
    const resolved = resolveMoversSelection(stale, providers, {});
    expect(resolved).toEqual({
      provider: "aws",
      category: "compute",
      regions: [],
      period_weeks: 4,
    });
    expect(moversNeedCleaning(stale, resolved)).toBe(true);
    const gone = {
      provider: "aws" as const,
      category: "all" as const,
      regions: ["us-east-1", "eu-gone-1"],
      period_weeks: 52 as const,
    };
    expect(resolveMoversSelection(gone, providers, { aws: ["us-east-1"] })?.regions).toEqual([
      "us-east-1",
    ]);
  });

  it("formats and explains", () => {
    expect(formatChangePct(8.333)).toBe("+8.33%");
    expect(formatChangePct(-10)).toBe("−10.00%");
    expect(moversNote({ ...base, weeks_available: 52 })).toBe(
      "Compares 2026-09-07 r1 with 2026-10-12 r1, 52 weeks.",
    );
    expect(moversNote({ ...base, status: "not_enough_history", from_snapshot: null })).toMatch(
      /Not enough history/,
    );
  });
});

describe("TrendsPage movers Reset (019, FR-020)", () => {
  beforeEach(() => {
    getTrendMovers.mockReset();
    getTrendMovers.mockResolvedValue(base);
    patchSection.mockClear();
  });

  it("restores the movers defaults without touching the charts section", async () => {
    const { TrendsPage } = await import("../../src/pages/TrendsPage");
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <TrendsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // The stored movers selection is used.
    await waitFor(() =>
      expect(getTrendMovers).toHaveBeenCalledWith({
        provider: "gcp",
        category: "storage",
        regions: ["us-east1"],
        period_weeks: 4,
      }),
    );
    const movers = screen.getByRole("heading", { name: "Biggest movers" }).parentElement!;
    fireEvent.click(within(movers).getByRole("button", { name: /Reset/ }));
    expect(patchSection.mock.calls).toEqual([["trends.movers", null]]);
  });
});
