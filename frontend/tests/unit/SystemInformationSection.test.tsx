import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type SystemInfo } from "../../src/api/client";
import { SystemInformationSection } from "../../src/components/admin/SystemInformationSection";

function info(overrides: Partial<SystemInfo> = {}): SystemInfo {
  return {
    active_snapshot_date: "2026-09-24",
    pinned: false,
    last_check_at: "2026-09-26T21:05:00Z",
    last_check_error: null,
    check_interval_seconds: 300,
    waiting_snapshots: [],
    issues: [],
    ...overrides,
  };
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SystemInformationSection />
    </QueryClientProvider>,
  );
}

describe("SystemInformationSection (016, US5)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the active snapshot and a Pinned badge when pinned", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info({ pinned: true }));
    renderSection();
    expect(await screen.findByText("2026-09-24")).toBeInTheDocument();
    expect(screen.getByText("Pinned")).toBeInTheDocument();
  });

  it("shows a waiting snapshot with its reason", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        waiting_snapshots: [
          { snapshot_date: "2026-09-27", reason: "no completion marker in price_fact" },
        ],
      }),
    );
    renderSection();
    expect(
      await screen.findByText("2026-09-27 — no completion marker in price_fact"),
    ).toBeInTheDocument();
  });

  it("lists missing-icon and missing-region issues, marking new services", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        issues: [
          {
            kind: "missing_regions",
            snapshot_date: "2026-09-24",
            message: "lost regions",
            regions: ["eu-west-2", "us-west-1"],
            service_code: null,
            service_name: null,
            is_new: null,
          },
          {
            kind: "missing_icon",
            snapshot_date: "2026-09-24",
            message: "no icon",
            service_code: "ZZNew",
            service_name: "Brand New Service",
            is_new: true,
            regions: null,
          },
        ],
      }),
    );
    renderSection();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("eu-west-2, us-west-1")).toBeInTheDocument();
    const row = within(table).getByText("ZZNew — Brand New Service").closest("tr") as HTMLElement;
    expect(within(row).getByText("New")).toBeInTheDocument();
  });

  it("says so when there are no issues", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    expect(await screen.findByText("No issues.")).toBeInTheDocument();
  });
});
