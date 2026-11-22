# Contract: `GET /admin/system-info` changes

Admin only, as today. Only the fields below change.

## `providers.<p>.history`

`HistoryOut | null`. `null` when that provider's history state can't be read; the rest of the
response is unaffected (FR-013). The shown states are in [data-model.md](../data-model.md#3-historyout-existing-now-nullable-per-provider).

## `providers.<p>.issues[]` and the top-level `issues[]`

Each issue gains `provider`. The top-level `issues` (today AWS's) becomes every provider's
issues: AWS, then GCP, then Azure; within a provider, new services first, then by code.

```json
{ "provider": "gcp", "kind": "missing_icon", "snapshot_date": "2026-11-16",
  "service_code": "6F81-5844-456A", "service_name": "Example Service", "is_new": true,
  "message": "Example Service has no icon; it shows the generic GCP tile on the canvas." }

{ "provider": "gcp", "kind": "marketplace_without_icons", "snapshot_date": "2026-11-16",
  "count": 1648,
  "message": "1,648 Marketplace and third-party GCP services have no icon (not listed)." }
```

- `missing_icon`: first-party services whose ID has no icon in the provider's map.
- `marketplace_without_icons`: at most one per provider, only when the count is above 0; GCP
  only in today's data.
- A provider with no active snapshot has no icon issues (FR-016).
- `missing_regions` issues are unchanged apart from `provider`.

## Admin page

- System Information's provider rows gain a **Trends history** cell (the states above).
- The Issues table gains a **Provider** column. The `marketplace_without_icons` row shows its
  message in place of a service code and name.
