import { useQuery } from "@tanstack/react-query";

import { api, type SystemInfo } from "../../api/client";
import { Badge } from "../ui/badge";

type Issue = SystemInfo["issues"][number];

const ISSUE_TYPE_LABELS: Record<Issue["kind"], string> = {
  pinned_incomplete: "Pinned snapshot",
  missing_regions: "Missing regions",
  missing_icon: "Missing icon",
};

function issueDetail(issue: Issue): string {
  if (issue.kind === "missing_icon") {
    return issue.service_name && issue.service_name !== issue.service_code
      ? `${issue.service_code} — ${issue.service_name}`
      : (issue.service_code ?? "");
  }
  if (issue.kind === "missing_regions") return (issue.regions ?? []).join(", ");
  return issue.message;
}

/**
 * The Admin tab's System Information section (016-canvas-icon-layout, US5: FR-020–FR-022,
 * contracts/ui.md §E): which pricing snapshot every lookup uses (and whether it's pinned), when
 * the background check last ran, any newer snapshot waiting to be complete, and an Issues
 * table of non-blocking problems — services with no canvas icon, regions a new snapshot lost,
 * or a pinned snapshot without completion markers. Refreshes every minute while open.
 */
export function SystemInformationSection() {
  const info = useQuery({
    queryKey: ["systemInfo"],
    queryFn: api.getSystemInfo,
    refetchInterval: 60_000,
  });

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

      {info.data && (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-2xs">
            <dt className="text-muted-foreground">Active pricing snapshot</dt>
            <dd className="flex items-center gap-1.5">
              {info.data.active_snapshot_date ?? "None"}
              {info.data.pinned && <Badge variant="secondary">Pinned</Badge>}
            </dd>
            <dt className="text-muted-foreground">Last checked</dt>
            <dd>
              {info.data.last_check_at
                ? new Date(info.data.last_check_at).toLocaleString()
                : "Not yet"}
            </dd>
            {info.data.waiting_snapshots.map((w) => (
              <div key={w.snapshot_date} className="contents">
                <dt className="text-muted-foreground">Waiting</dt>
                <dd>
                  {w.snapshot_date} — {w.reason}
                </dd>
              </div>
            ))}
          </dl>
          {info.data.last_check_error && (
            <p className="text-2xs text-destructive">
              Last check failed: {info.data.last_check_error}
            </p>
          )}

          <h3 className="text-2xs font-semibold">Issues</h3>
          {info.data.issues.length === 0 ? (
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
                {info.data.issues.map((issue, i) => (
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
