import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type SystemInfo } from "../../api/client";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

type Issue = SystemInfo["issues"][number];
type FailedRegion = NonNullable<SystemInfo["latest_run"]>["failed_regions"][number];

const ISSUE_TYPE_LABELS: Record<Issue["kind"], string> = {
  missing_regions: "Missing regions",
  missing_icon: "Missing icon",
};

const RUN_STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  succeeded: "secondary",
  partial: "destructive",
  failed: "destructive",
  purged: "secondary",
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
  return issue.message;
}

function failedList(regions: FailedRegion[]): string {
  return regions.map((f) => `${f.region}: ${f.reason}`).join("; ");
}

function mib(bytes: number): string {
  return `${Math.round(bytes / MIB)} MiB`;
}

/**
 * The Admin tab's System Information section (016-canvas-icon-layout, US5: FR-020–FR-022;
 * 018-app-cloud-deployment, FR-012, FR-014, contracts/admin-api.md): which environment and
 * release this is, where pricing data comes from, the active snapshot (date, revision, pipeline
 * run, regions), the latest pipeline run and any refused manifest, the S3 cache, the last check
 * with a **Check now** button, and an Issues table. Refreshes every minute while open.
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
  const active = data?.active;

  return (
    <section aria-labelledby="system-information" className="flex max-w-2xl flex-col gap-3">
      <h2 id="system-information" className="text-xs font-semibold">
        System Information
      </h2>

      {info.isError && (
        <p className="text-2xs text-destructive">
          Could not load system information: {info.error.message}
        </p>
      )}

      {data && (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-2xs">
            <dt className="text-muted-foreground">Deployment</dt>
            <dd>
              {data.deployment.environment} — {data.deployment.release}
            </dd>
            <dt className="text-muted-foreground">Pricing data source</dt>
            <dd>
              {data.source.kind} — {data.source.location}
            </dd>
            <dt className="text-muted-foreground">Active pricing snapshot</dt>
            <dd className="flex items-center gap-1.5">
              {active ? `${active.snapshot_date} r${active.revision}` : "None"}
              {active?.pinned && <Badge variant="secondary">Pinned</Badge>}
            </dd>
            {active && (
              <>
                <dt className="text-muted-foreground">Pipeline run</dt>
                <dd>
                  {active.run_id} (pipeline {active.pipeline_version}, created{" "}
                  {new Date(active.created_at).toLocaleString()})
                </dd>
                <dt className="text-muted-foreground">Regions</dt>
                <dd>{active.regions.join(", ")}</dd>
                {active.failed_regions.length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Failed regions</dt>
                    <dd>{failedList(active.failed_regions)}</dd>
                  </>
                )}
              </>
            )}
            {data.latest_run && (
              <>
                <dt className="text-muted-foreground">Latest pipeline run</dt>
                <dd className="flex flex-wrap items-center gap-1.5">
                  {data.latest_run.snapshot_date} r{data.latest_run.revision}
                  <Badge variant={RUN_STATUS_VARIANT[data.latest_run.status] ?? "secondary"}>
                    {data.latest_run.status}
                  </Badge>
                  {data.latest_run.failed_regions.length > 0 && (
                    <span>{failedList(data.latest_run.failed_regions)}</span>
                  )}
                </dd>
              </>
            )}
            {data.rejected && (
              <>
                <dt className="text-muted-foreground">Last refused manifest</dt>
                <dd className="text-destructive">
                  {data.rejected.snapshot_date ?? "?"}
                  {data.rejected.revision != null ? ` r${data.rejected.revision}` : ""} —{" "}
                  {data.rejected.reason}
                </dd>
              </>
            )}
            <dt className="text-muted-foreground">Last checked</dt>
            <dd className="flex items-center gap-2">
              {data.last_check_at ? new Date(data.last_check_at).toLocaleString() : "Not yet"}
              <Button size="sm" variant="outline" onClick={checkNow} disabled={checking}>
                Check now
              </Button>
            </dd>
          </dl>
          {checkError && <p className="text-2xs text-destructive">{checkError}</p>}
          {data.last_check_error && (
            <p className="text-2xs text-destructive">
              Last check failed: {data.last_check_error}
            </p>
          )}

          {data.cache && (
            <>
              <h3 className="text-2xs font-semibold">Cache</h3>
              <p className="text-2xs">
                {mib(data.cache.total_bytes)} of {mib(data.cache.max_bytes)} (
                {Math.round((100 * data.cache.total_bytes) / data.cache.max_bytes)}%)
              </p>
              <ul className="text-2xs">
                {data.cache.entries.map((e) => (
                  <li key={`${e.snapshot_date}-${e.revision}`}>
                    {e.snapshot_date} r{e.revision} — {e.state}, {mib(e.bytes)}
                  </li>
                ))}
              </ul>
            </>
          )}

          <h3 className="text-2xs font-semibold">Issues</h3>
          {data.issues.length === 0 ? (
            <p className="text-2xs text-muted-foreground">No issues.</p>
          ) : (
            <table className="w-full border-collapse text-2xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1.5">Type</th>
                  <th className="py-1.5">Detail</th>
                  <th className="py-1.5">Snapshot</th>
                  <th className="py-1.5">New</th>
                </tr>
              </thead>
              <tbody>
                {data.issues.map((issue, i) => (
                  <tr
                    key={`${issue.kind}-${issue.service_code ?? i}`}
                    className="border-b border-border"
                  >
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
          )}
        </>
      )}
    </section>
  );
}
