# Contract: Admin API changes

The two admin endpoints are admin-only (`AdminUser`), as today. The frontend types are regenerated from OpenAPI (constitution IV). The existing `api-contract-drift` CI job enforces it.

## `GET /api/v1/admin/system-info` (changed)

```jsonc
{
  "deployment": { "environment": "prod", "release": "v1.4.0" },
  "source": { "kind": "s3", "location": "s3://cloud-pricing-data-prod-g08a9i", "provider": "aws" },
  "active": {                       // null when no usable snapshot
    "snapshot_date": "2026-10-05",
    "revision": 2,
    "run_id": "20261005T141210Z-9c41e2",
    "pipeline_version": "1.3.0",
    "created_at": "2026-10-05T14:19:03Z",
    "pinned": false,
    "regions": ["eu-west-1", "us-east-1"],
    "failed_regions": []
  },
  "latest_run": {                   // newest dated manifest of any status; null if none
    "snapshot_date": "2026-10-12",
    "revision": 1,
    "status": "partial",            // succeeded | partial | failed | purged
    "failed_regions": [{ "region": "ap-northeast-1", "reason": "…", "attempts": 3 }]
  },
  "rejected": null,                 // or { "snapshot_date", "revision", "reason" } for the last refused manifest
  "cache": {                        // null for a local source
    "total_bytes": 152043520,
    "max_bytes": 1073741824,
    "entries": [{ "snapshot_date": "2026-10-05", "revision": 2, "state": "active", "bytes": 152043520 }]
  },
  "last_check_at": "2026-10-12T09:00:00Z",
  "last_check_error": null,
  "check_interval_seconds": 300,
  "issues": [ /* IssueOut, kind: "missing_icon" | "missing_regions" */ ]
}
```

- **Removed**: `waiting_snapshots`, `active_snapshot_date` (now `active.snapshot_date`), `pinned` (now `active.pinned`), and the issue kind `pinned_incomplete`.
- **`source.location`** never contains credentials. S3 locations are shown as the bucket and prefix only.

## `POST /api/v1/admin/pricing-snapshot/check` (new)

Runs one check now, serialized with the background check (FR-012). It returns `202` immediately with `{"started": true}`, or `409` with `{"error": "check_in_progress"}` if one is already running. The result appears in `system-info` once the check finishes, and the Admin tab polls it.

## `GET /health` (changed, public)

Still unauthenticated, now with a typed `HealthOut` model:

```jsonc
{ "status": "ok", "pricing": "ok", "pricing_reason": null }   // pricing: "ok" | "unavailable"
```

`pricing_reason` is a short fixed phrase, such as `"no snapshot available"` or `"verification failed"`. It never contains a location, a credential or an exception text. `ops health` reads it, so the health check never needs a login token (FR-028).

## Pricing and catalog responses (changed)

`CalculationResult` and `CatalogSearchResult` keep `snapshot_date` and add `snapshot_revision: int` (FR-059). Both come from the same `ActiveSnapshot` the request used. The frontend shows the revision wherever it shows the snapshot date.

## Unchanged behavior

Pricing endpoints return the existing `503 pricing_data_unavailable` when there is no active snapshot (FR-013), and a missing SKU price shows the existing error (FR-017).
