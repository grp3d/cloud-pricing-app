import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TrendSeries } from "../../src/api/client";
import { TrendsChartPanel } from "../../src/components/trends/TrendsChartPanel";

function point(
  week: string,
  increased: number | null,
  decreased: number | null,
  compared: number | null,
  gap = false,
) {
  return {
    week,
    from_snapshot: "x r1",
    to_snapshot: `${week} r1`,
    increased,
    decreased,
    increased_pct: compared ? ((increased ?? 0) * 100) / compared : null,
    decreased_pct: compared ? ((decreased ?? 0) * 100) / compared : null,
    compared,
    excluded: compared == null ? null : 1,
    gap,
  };
}

const aws: TrendSeries = {
  provider: "aws",
  regions: ["us-east-1", "us-west-2"],
  status: "ok",
  reason: null,
  weeks_built: 3,
  weeks_total: 3,
  points: [
    point("2026-09-14", 0, 0, 10),
    point("2026-09-21", null, null, null),
    point("2026-10-05", 1, 2, 10, true),
  ],
};

describe("TrendsChartPanel (019, FR-012, FR-013)", () => {
  it("draws one up/down series per provider, titled with its regions", () => {
    const gcp: TrendSeries = {
      ...aws,
      provider: "gcp",
      regions: [],
      points: [point("2026-10-12", 0, 1, 4)],
    };
    render(<TrendsChartPanel series={[aws, gcp]} />);
    expect(screen.getByRole("region", { name: "AWS — us-east-1, us-west-2" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "GCP — all regions" })).toBeInTheDocument();
    expect(screen.getByLabelText("Legend").textContent).toMatch(/Up.*Down/);
  });

  it("shows no data apart from zero, and marks the week after a gap", () => {
    render(<TrendsChartPanel series={[aws]} />);
    const rows = within(screen.getByRole("table", { name: /AWS/ })).getAllByRole("row");
    expect(rows[1].textContent).toBe("2026-09-1400101");
    expect(rows[2].textContent).toContain("No data");
    expect(rows[3].textContent).toContain("2026-10-05 (after a gap)");
  });

  it("explains a series with too little history, one still building and one unavailable", () => {
    render(
      <TrendsChartPanel
        series={[
          { ...aws, provider: "aws", status: "not_enough_history", points: [] },
          { ...aws, provider: "azure", status: "building", weeks_built: 2, weeks_total: 9 },
          {
            ...aws,
            provider: "gcp",
            status: "provider_unavailable",
            reason: "snapshot rejected",
            points: [],
          },
        ]}
      />,
    );
    expect(screen.getByText(/Not enough history yet/)).toBeInTheDocument();
    expect(screen.getByText("Building history (2 of 9 weeks)")).toBeInTheDocument();
    expect(screen.getByText("Pricing data unavailable: snapshot rejected.")).toBeInTheDocument();
    // A building series still shows the weeks built so far.
    expect(screen.getByRole("table", { name: /Azure/ })).toBeInTheDocument();
  });
});
