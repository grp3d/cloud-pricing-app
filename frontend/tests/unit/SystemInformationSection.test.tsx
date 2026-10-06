import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type SystemInfo } from "../../src/api/client";
import { SystemInformationSection } from "../../src/components/admin/SystemInformationSection";

function info(overrides: Partial<SystemInfo> = {}): SystemInfo {
  return {
    deployment: { environment: "prod", release: "v1.4.0" },
    source: { kind: "local", location: "/data/pipeline", provider: "aws" },
    active: {
      snapshot_date: "2026-09-24",
      revision: 2,
      run_id: "20260924T141210Z-9c41e2",
      pipeline_version: "1.3.0",
      created_at: "2026-09-24T14:19:03Z",
      pinned: false,
      regions: ["eu-west-1", "us-east-1"],
      failed_regions: [],
    },
    latest_run: { snapshot_date: "2026-09-24", revision: 2, status: "succeeded", failed_regions: [] },
    rejected: null,
    cache: null,
    last_check_at: "2026-09-26T21:05:00Z",
    last_check_error: null,
    check_interval_seconds: 300,
    issues: [],
    ...overrides,
  };
}

async function activeRow(): Promise<string> {
  const term = await screen.findByText("Active pricing snapshot");
  return term.nextElementSibling?.textContent ?? "";
}

function renderSection(props: { pollMs?: number } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SystemInformationSection {...props} />
    </QueryClientProvider>,
  );
}

describe("SystemInformationSection (016, US5; 018, FR-012/FR-014)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the deployment, the source and the active snapshot with its revision", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    expect(await activeRow()).toBe("2026-09-24 r2");
    expect(screen.getByText("prod — v1.4.0")).toBeInTheDocument();
    expect(screen.getByText("local — /data/pipeline")).toBeInTheDocument();
    expect(screen.getByText("eu-west-1, us-east-1")).toBeInTheDocument();
    expect(screen.getByText(/1\.3\.0/)).toBeInTheDocument();
  });

  it("shows a Pinned badge when pinned", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({ active: { ...info().active!, pinned: true } }),
    );
    renderSection();
    expect(await screen.findByText("Pinned")).toBeInTheDocument();
  });

  it("says when there is no usable snapshot", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({ active: null, last_check_error: "no snapshot available" }),
    );
    renderSection();
    expect(await screen.findByText("None")).toBeInTheDocument();
    expect(screen.getByText("Last check failed: no snapshot available")).toBeInTheDocument();
  });

  it("hides the cache for a local source", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(info());
    renderSection();
    await activeRow();
    expect(screen.queryByText("Cache")).not.toBeInTheDocument();
  });

  it("shows the cache entries and how full it is for an S3 source", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        source: { kind: "s3", location: "s3://cloud-pricing-data-prod", provider: "aws" },
        cache: {
          total_bytes: 268435456,
          max_bytes: 1073741824,
          entries: [
            { snapshot_date: "2026-09-17", revision: 1, state: "cached", bytes: 134217728 },
            { snapshot_date: "2026-09-24", revision: 2, state: "active", bytes: 134217728 },
          ],
        },
      }),
    );
    renderSection();
    expect(await screen.findByText("Cache")).toBeInTheDocument();
    expect(screen.getByText("256 MiB of 1024 MiB (25%)")).toBeInTheDocument();
    expect(screen.getByText("2026-09-17 r1 — cached, 128 MiB")).toBeInTheDocument();
    expect(screen.getByText("2026-09-24 r2 — active, 128 MiB")).toBeInTheDocument();
  });

  it("shows a partial latest run with its failed regions and reasons", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        latest_run: {
          snapshot_date: "2026-10-01",
          revision: 1,
          status: "partial",
          failed_regions: [{ region: "ap-northeast-1", reason: "download timed out", attempts: 3 }],
        },
      }),
    );
    renderSection();
    expect(await screen.findByText("partial")).toBeInTheDocument();
    expect(screen.getByText("ap-northeast-1: download timed out")).toBeInTheDocument();
  });

  it("shows the last rejected manifest", async () => {
    vi.spyOn(api, "getSystemInfo").mockResolvedValue(
      info({
        rejected: { snapshot_date: "2026-10-01", revision: 1, reason: "status is partial" },
      }),
    );
    renderSection();
    expect(await screen.findByText("2026-10-01 r1 — status is partial")).toBeInTheDocument();
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
    vi.spyOn(api, "startSnapshotCheck").mockRejectedValue(
      new Error("A check is already running."),
    );
    renderSection();
    fireEvent.click(await screen.findByRole("button", { name: "Check now" }));
    expect(await screen.findByText("A check is already running.")).toBeInTheDocument();
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
