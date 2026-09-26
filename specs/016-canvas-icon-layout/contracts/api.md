# API Contract Changes: 016-canvas-icon-layout

This feature makes two API changes:
- a new admin endpoint;
- a new optional field on an existing PATCH.

All shapes are Pydantic models in `backend/src/models/schemas.py`, and
`frontend/src/api/generated/schema.d.ts` is regenerated from them (Principle IV).

---

## 1. `GET /api/v1/admin/system-info` (new)

**Auth**: admin only (`require_admin`). A non-admin user gets 403, and a request with no session
gets 401, the same as the other `/admin/*` routes.

**200 response** (`SystemInfoOut`):

```jsonc
{
  "active_snapshot_date": "2026-09-24",        // string (ISO date) | null
  "pinned": false,                              // true when ACTIVE_SNAPSHOT_DATE is set
  "last_check_at": "2026-09-26T21:05:00Z",      // string (ISO datetime, UTC) | null
  "last_check_error": null,                     // string | null
  "check_interval_seconds": 300,
  "waiting_snapshots": [
    { "snapshot_date": "2026-09-27", "reason": "no completion marker in price_fact" }
  ],
  "issues": [
    {
      "kind": "missing_icon",                   // "missing_icon" | "missing_regions" | "pinned_incomplete"
      "snapshot_date": "2026-09-24",
      "service_code": "AmazonHoneycode",        // missing_icon only, else null
      "service_name": "Amazon Honeycode",       // missing_icon only, else null
      "is_new": false,                          // missing_icon only, else null
      "regions": null,                          // missing_regions only: ["eu-west-2"]
      "message": "AmazonHoneycode has no icon; it shows the generic AWS icon on the canvas."
    }
  ]
}
```

**Behavior**:
- It reads the in-memory Active Snapshot State (data-model.md §1). It never triggers a check or
  reads Parquet, so it is always fast.
- Issues are ordered as described in data-model.md §2.

**Contract tests (written first)**:
1. An admin gets 200 with the shape above, and `active_snapshot_date` equals the fixture's
   complete date.
2. A non-admin gets 403.
3. With a fixture service code that isn't in the icon map, `issues` has a `missing_icon` entry for
   it.

---

## 2. `PATCH /api/v1/sku-selections/{sku_selection_id}` (extended)

**Request** (`SKUSelectionUpdate`): the existing optional fields, plus one new optional field:

```jsonc
{ "collection_id": "uuid" }   // optional; moves the service to that box
```

The new field can be combined with the pricing-input fields, but the canvas only ever sends it
alone.

**Responses**:

| Status | When | Body |
|---|---|---|
| 200 | Moved (and/or inputs updated) | `SKUSelectionOut`, unchanged shape |
| 400 | The selection belongs to a connector, not a box | `{"error":"not_movable","message":"Services attached to a connector can't be moved to a box."}` |
| 404 | The target box doesn't exist, is deleted, or belongs to another architecture or user | `{"detail":"Collection not found"}` |
| 409 | The target box is in a different region | `{"error":"region_mismatch","message":"\"<service_code>\" is in <source region> and can only move to a box in the same region."}` |

**Contract tests (written first)**:
1. A move between two same-region boxes in one architecture returns 200. `GET /architectures/{id}`
   then shows the selection under the target box.
2. A move to a box in another region returns 409 and nothing changes.
3. A move to a box in another architecture returns 404.
4. A connector-owned selection returns 400.
5. A move to the same box returns 200 and changes nothing.

---

## 3. Unchanged endpoints whose snapshot date now comes from the active snapshot

The following keep their request and response shapes, but now use the active snapshot date,
resolved once per request (FR-014, FR-019):
- catalog search
- regions list
- architecture detail (units, attributes, product family)
- SKU selection create, update and attach
- calculate
- calculate-snapshot

If there is no active date, each returns the existing 503 `pricing_data_unavailable`.
