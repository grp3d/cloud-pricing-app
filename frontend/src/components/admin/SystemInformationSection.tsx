import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, type SystemInfo } from "../../api/client";
import { PROVIDER_LABELS } from "../../lib/providerPricing";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { AdminTabs } from "./AdminTabs";

type Issue = SystemInfo["issues"][number];
type FailedRegion = NonNullable<SystemInfo["latest_run"]>["failed_regions"][number];

const ISSUE_TYPE_LABELS: Record<Issue["kind"], string> = {
  missing_regions: "Missing regions",
  missing_icon: "Missing icon",
  marketplace_without_icons: "Marketplace, no icon",
};

const PROVIDER_STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  current: "default",
  partial: "secondary",
  stale: "secondary",
  failed: "destructive",
  none: "secondary",
};

const MIB = 1024 * 1024;
// 018-app-cloud-deployment: after Check now, how long to keep refreshing for its result.
const CHECK_WAIT_MS = 60_000;

function issueDetail(issue: Issue): string {
  if (issue.kind === "missing_icon") {
    return issue.service_name && issue.service_name !== issue.service_code
      ? `${issue.service_code} — ${issue.service_name}`
      : (issue.service_code ?? "");
  }
  if (issue.kind === "missing_regions") return (issue.regions ?? []).join(", ");
  // 027: the Marketplace count line says how many, in its message.
  return issue.message;
}

type History = NonNullable<SystemInfo["providers"]>[string]["history"];

/** 027 (FR-012, FR-013, data-model §3): one provider's Trends history, in order of precedence. */
function historyText(history: History): string {
  if (!history) return "Unavailable";
  const built = history.last_built_at ? `last built ${history.last_built_at.slice(0, 10)}` : null;
  if (history.backfill === "running") {
    return `Building (${history.weeks_built} of ${history.weeks_total} weeks)`;
  }
  if (history.backfill === "failed") return `Failed: ${history.last_error ?? "no error recorded"}`;
  if (history.weeks_total === 0) return "No history yet";
  if (history.gaps.length > 0) {
    const missing = `${history.gaps.length} week${history.gaps.length === 1 ? "" : "s"} missing`;
    const detail = [`${history.weeks_built} of ${history.weeks_total} built`, built]
      .filter(Boolean)
      .join(", ");
    return `${missing} (${detail})`;
  }
  return `Complete: ${history.weeks_built} weeks${built ? `, ${built}` : ""}`;
}

function failedList(regions: FailedRegion[]): string {
  return regions.map((f) => `${f.region}: ${f.reason}`).join("; ");
}

function mib(bytes: number): string {
  return `${Math.round(bytes / MIB)} MiB`;
}

/**
 * The Admin tab's System Information section (016-canvas-icon-layout, US5: FR-020–FR-022;
 * 018-app-cloud-deployment, FR-012, FR-014, contracts/admin-api.md). 027 (US6): at the top, what
 * is app-wide (environment and release, where pricing data comes from, the last check with a
 * **Check now** button, and the S3 cache across every provider); below, the **Providers** tab
 * (each provider's snapshot, run, regions and Trends history) and the **Issues** tab. Refreshes
 * every minute while open.
 */
export function SystemInformationSection({ pollMs = 2_000 }: { pollMs?: number }) {
  const queryClient = useQueryClient();
  const info = useQuery({
    queryKey: ["systemInfo"],
    queryFn: api.getSystemInfo,
    refetchInterval: 60_000,
  });
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  async function checkNow() {
    setCheckError(null);
    const before = info.data?.last_check_at ?? null;
    try {
      await api.startSnapshotCheck();
    } catch (error) {
      setCheckError((error as Error).message);
      return;
    }
    setChecking(true);
    const deadline = Date.now() + CHECK_WAIT_MS;
    try {
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, pollMs));
        const fresh = await queryClient.fetchQuery({
          queryKey: ["systemInfo"],
          queryFn: api.getSystemInfo,
          staleTime: 0,
        });
        if (fresh.last_check_at !== before) break;
      }
    } finally {
      setChecking(false);
    }
  }

  const data = info.data;

  return (
    <section aria-labelledby="system-information" className="flex max-w-3xl flex-col gap-3">
      <h2 id="system-information" className="sr-only">
        System Information
      </h2>

      {info.isError && (
        <p className="text-2xs text-destructive">
          Could not load system information: {info.error.message}
        </p>
      )}

      {data && (
        <>
          {/* 027 (US6, FR-017): only what is app-wide; each provider's detail is in its row. */}
          <dl
            aria-label="App-wide"
            className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-2xs"
          >
            <dt className="text-muted-foreground">Deployment</dt>
            <dd>
              {data.deployment.environment} — {data.deployment.release}
            </dd>
            <dt className="text-muted-foreground">Pricing data source</dt>
            <dd>
              {data.source.kind} — {data.source.location}
            </dd>
            <dt className="text-muted-foreground">Last checked</dt>
            <dd className="flex items-center gap-2">
              {data.last_check_at ? new Date(data.last_check_at).toLocaleString() : "Not yet"}
              <Button size="sm" variant="outline" onClick={checkNow} disabled={checking}>
                Check now
              </Button>
            </dd>
          </dl>
          {checkError && <p className="text-2xs text-destructive">{checkError}</p>}

          {data.cache && (
            <>
              <h3 className="text-2xs font-semibold">Cache</h3>
              <p className="text-2xs">
                {mib(data.cache.total_bytes)} of {mib(data.cache.max_bytes)} (
                {Math.round((100 * data.cache.total_bytes) / data.cache.max_bytes)}%)
              </p>
              <ul className="text-2xs">
                {data.cache.entries.map((e) => (
                  <li key={`${e.provider}-${e.snapshot_date}-${e.revision}`}>
                    {PROVIDER_LABELS[e.provider]} {e.snapshot_date} r{e.revision} — {e.state},{" "}
                    {mib(e.bytes)}
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* 027 (US6, FR-019): Providers (the default) and Issues, kept in `?section=`. */}
          <AdminTabs
            param="section"
            label="System Information sections"
            idPrefix="system"
            tabs={[
              {
                id: "providers",
                label: "Providers",
                content: <ProvidersTable providers={data.providers ?? {}} />,
              },
              {
                id: "issues",
                label: `Issues (${data.issues.length})`,
                content: <IssuesTable issues={data.issues} />,
              },
            ]}
          />
        </>
      )}
    </section>
  );
}

type ProviderInfo = NonNullable<SystemInfo["providers"]>[string];

/** 019 (FR-009) and 027 (US6, FR-018): each provider's snapshot on its own row, with all its
 * detail; one provider's broken data never hides the others'. */
function ProvidersTable({ providers }: { providers: Record<string, ProviderInfo> }) {
  return (
    <table aria-label="Provider snapshots" className="w-full border-collapse text-2xs">
      <thead>
        <tr className="border-b border-border text-left align-bottom text-muted-foreground">
          <th className="py-1.5 pr-2">Provider</th>
          <th className="py-1.5 pr-2">Status</th>
          <th className="py-1.5 pr-2">Active snapshot</th>
          <th className="py-1.5 pr-2">Regions</th>
          <th className="py-1.5 pr-2">Trends history</th>
          <th className="py-1.5">Detail</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(providers).map(([code, p]) => {
          const active = p.active_snapshot;
          const detail = [
            p.reason,
            active && active.failed_regions.length > 0
              ? `failed regions: ${failedList(active.failed_regions)}`
              : null,
            p.latest_run && p.latest_run.status !== "succeeded"
              ? `latest run ${p.latest_run.snapshot_date} r${p.latest_run.revision} ` +
                `${p.latest_run.status}` +
                (p.latest_run.failed_regions.length > 0
                  ? ` (${failedList(p.latest_run.failed_regions)})`
                  : "")
              : null,
            p.rejected
              ? `refused ${p.rejected.snapshot_date ?? "?"}` +
                `${p.rejected.revision != null ? ` r${p.rejected.revision}` : ""}: ` +
                p.rejected.reason
              : null,
            p.last_check_error ? `last check failed: ${p.last_check_error}` : null,
            p.issues.length > 0 ? `${p.issues.length} issue(s)` : null,
          ].filter(Boolean);
          return (
            <tr key={code} className="border-b border-border align-top">
              <td className="py-1.5 pr-2">{p.name}</td>
              <td className="py-1.5 pr-2">
                <Badge variant={PROVIDER_STATUS_VARIANT[p.status] ?? "secondary"}>
                  {p.status}
                </Badge>
              </td>
              <td className="py-1.5 pr-2">
                {active ? (
                  <>
                    <span className="flex items-center gap-1.5">
                      {`${active.snapshot_date} r${active.revision}`}
                      {active.pinned && <Badge variant="secondary">Pinned</Badge>}
                    </span>
                    <span className="block text-muted-foreground">
                      {`run ${active.run_id}, pipeline ${active.pipeline_version}`}
                    </span>
                  </>
                ) : (
                  "None"
                )}
              </td>
              <td className="py-1.5 pr-2">{active?.regions.join(", ") ?? "—"}</td>
              <td className="py-1.5 pr-2">{historyText(p.history)}</td>
              <td className="py-1.5">{detail.join("; ") || "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const ISSUE_FILTERS = ["all", "aws", "gcp", "azure"] as const;
type IssueFilter = (typeof ISSUE_FILTERS)[number];

/** 016 (US5) and 027 (US5, US6): every provider's issues, AWS, then GCP, then Azure, filtered by
 * provider (All by default, kept in `?issues=`) and scrolling inside a fixed height with the
 * header kept in view. */
function IssuesTable({ issues }: { issues: Issue[] }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("issues");
  const filter: IssueFilter = ISSUE_FILTERS.includes(requested as IssueFilter)
    ? (requested as IssueFilter)
    : "all";
  const shown = filter === "all" ? issues : issues.filter((i) => i.provider === filter);

  function choose(next: IssueFilter) {
    setParams(
      (p) => {
        const out = new URLSearchParams(p);
        if (next === "all") out.delete("issues");
        else out.set("issues", next);
        return out;
      },
      { replace: true },
    );
  }

  if (issues.length === 0) return <p className="text-2xs text-muted-foreground">No issues.</p>;
  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Filter issues by provider"
        className="flex w-fit items-center gap-0.5 rounded-lg bg-muted p-0.5"
      >
        {ISSUE_FILTERS.map((code) => {
          const count =
            code === "all" ? issues.length : issues.filter((i) => i.provider === code).length;
          const label = code === "all" ? "All" : PROVIDER_LABELS[code];
          const selected = code === filter;
          return (
            <button
              key={code}
              type="button"
              aria-pressed={selected}
              onClick={() => choose(code)}
              className={`focus-ring h-6 rounded-md px-2 text-2xs font-medium transition-colors ${
                selected
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {`${label} (${count})`}
            </button>
          );
        })}
      </div>
      {shown.length === 0 ? (
        <p className="text-2xs text-muted-foreground">
          No issues for {filter === "all" ? "any provider" : PROVIDER_LABELS[filter]}.
        </p>
      ) : (
        // Scrollable, so focusable for keyboard users (WCAG 2.1.1).
        <div
          role="region"
          aria-label="Issues list"
          tabIndex={0}
          className="focus-ring max-h-[min(32rem,60vh)] overflow-y-auto rounded-md"
        >
          <table aria-label="Issues" className="w-full border-collapse text-2xs">
            <thead className="sticky top-0 z-10 bg-background">
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="py-1.5">Provider</th>
                <th className="py-1.5">Type</th>
                <th className="py-1.5">Detail</th>
                <th className="py-1.5">Snapshot</th>
                <th className="py-1.5">New</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((issue, i) => (
                <tr
                  key={`${issue.provider}-${issue.kind}-${issue.service_code ?? i}`}
                  className="border-b border-border"
                >
                  <td className="py-1.5">{PROVIDER_LABELS[issue.provider]}</td>
                  <td className="py-1.5">{ISSUE_TYPE_LABELS[issue.kind]}</td>
                  <td className="py-1.5" title={issue.message}>
                    {issueDetail(issue)}
                  </td>
                  <td className="py-1.5">{issue.snapshot_date}</td>
                  <td className="py-1.5">
                    {issue.is_new ? <Badge variant="default">New</Badge> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
