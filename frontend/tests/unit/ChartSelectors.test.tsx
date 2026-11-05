import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Provider } from "../../src/api/client";
import { ChartSelectors } from "../../src/components/trends/ChartSelectors";
import { CHARTS_DEFAULTS, resolveChartSelection } from "../../src/lib/trends";

const providers: Provider[] = [
  {
    code: "aws",
    name: "AWS",
    active: true,
    status: "current",
    reason: null,
    snapshot_date: "2026-10-12",
    snapshot_revision: 1,
  },
  {
    code: "gcp",
    name: "GCP",
    active: true,
    status: "current",
    reason: null,
    snapshot_date: "2026-11-02",
    snapshot_revision: 1,
  },
  {
    code: "azure",
    name: "Azure",
    active: false,
    status: "failed",
    reason: "x",
    snapshot_date: null,
    snapshot_revision: null,
  },
];
const regions = {
  aws: [
    { code: "us-east-1", display_name: "us-east-1" },
    { code: "us-west-2", display_name: "us-west-2" },
  ],
  gcp: [{ code: "us-east1", display_name: "us-east1" }],
};

describe("ChartSelectors (019, FR-011, FR-020)", () => {
  it("lists regions under each selected provider and reports changes", () => {
    const onChange = vi.fn();
    const selection = {
      providers: [{ provider: "aws" as const, regions: [] }],
      category: "all" as const,
    };
    render(
      <ChartSelectors
        providers={providers.filter((p) => p.active)}
        regionsByProvider={regions}
        selection={selection}
        onChange={onChange}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText("All regions")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "us-west-2" }));
    expect(onChange).toHaveBeenLastCalledWith({
      providers: [{ provider: "aws", regions: ["us-west-2"] }],
      category: "all",
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "GCP" }));
    expect(onChange).toHaveBeenLastCalledWith({
      providers: [
        { provider: "aws", regions: [] },
        { provider: "gcp", regions: [] },
      ],
      category: "all",
    });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "storage" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...selection, category: "storage" });
    expect(screen.queryByRole("checkbox", { name: "Azure" })).toBeNull();
  });

  it("defaults to every active provider with all regions, dropping stale stored values", () => {
    expect(resolveChartSelection(null, providers, {})).toEqual({
      providers: [
        { provider: "aws", regions: [] },
        { provider: "gcp", regions: [] },
      ],
      category: "all",
    });
    expect(
      resolveChartSelection(
        {
          providers: [
            { provider: "azure", regions: [] },
            { provider: "aws", regions: ["us-east-1", "eu-gone-1"] },
          ],
          category: "compute",
        },
        providers,
        { aws: ["us-east-1", "us-west-2"] },
      ),
    ).toEqual({ providers: [{ provider: "aws", regions: ["us-east-1"] }], category: "compute" });
  });
});

// --- TrendsPage: Reset saves the defaults for the charts section only -------------------------

const patchSection = vi.fn();
vi.mock("../../src/lib/preferences", () => ({
  usePreferences: () => [
    {
      migrated_from_browser: true,
      trends: {
        charts: { providers: [{ provider: "aws", regions: ["us-east-1"] }], category: "storage" },
        movers: { provider: "gcp", category: "all", regions: [], period_weeks: 52 },
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
      getTrendSeries: vi.fn(async () => ({
        metric: "skus_changed",
        category: "storage",
        series: [],
      })),
      getTrendMovers: vi.fn(async () => null),
    },
  };
});

describe("TrendsPage Reset (019, FR-020)", () => {
  beforeEach(() => patchSection.mockClear());

  it("stores the chart defaults and nothing else", async () => {
    const { TrendsPage } = await import("../../src/pages/TrendsPage");
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <TrendsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const charts = (await screen.findByRole("heading", { name: "SKUs changed per week" }))
      .parentElement!.parentElement!;
    fireEvent.click(await within(charts).findByRole("button", { name: /Reset/ }));
    await waitFor(() => expect(patchSection).toHaveBeenCalled());
    expect(patchSection.mock.calls.map((c) => c[0])).toEqual(["trends.charts"]);
    expect(patchSection).toHaveBeenCalledWith("trends.charts", CHARTS_DEFAULTS);
  });
});
