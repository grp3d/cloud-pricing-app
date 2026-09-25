# API Contract: Admin Architecture Import/Export

All routes are under `/api/v1` and gated on `AdminUser` (`src/api/deps.py` → `require_admin`). A non-admin caller gets `403` and a missing or invalid token gets `401` (FR-025). The request and response models are Pydantic classes in `src/models/schemas.py`. The generated TypeScript types in `frontend/src/api/generated/schema.d.ts` MUST be regenerated, and CI's `check-api-types` MUST pass (Constitution IV).

---

## Changed: `GET /admin/users`

The response item `AdminUserOut` gains one field:

```json
{
  "id": "…", "username": "jdoe", "is_active": true, "has_password": true,
  "password_hash_suffix": "a1b2", "is_admin": false, "is_default_admin": false,
  "architecture_count": 3
}
```

`architecture_count` counts the user's architectures with `deleted_at IS NULL`.

---

## New: `GET /admin/users/{user_id}/architectures/export`

Returns all of the user's non-deleted architectures as an `ArchitectureExportFile` ([export-format.md](export-format.md)).

| Status | When |
|---|---|
| `200` | Body is an `ArchitectureExportFile`. `architectures` may be `[]`, but the UI never calls this route for a user with a count of 0. |
| `404` | `user_id` is unknown or is a guest identity (`username IS NULL`), matching `_get_named_user_or_404`. |

The server doesn't set a filename. The client names the download `<safe-username>_<YYYYMMDDTHHMMSS>.json` using its own clock (FR-013). In `safe-username`, every character outside `[A-Za-z0-9._-]` is replaced with `_`.

---

## New: `POST /admin/users/{user_id}/architectures/import`

**Request body**: `ArchitectureImportRequest`, a lenient envelope:

```json
{
  "format": "cloud-pricing-architectures",
  "format_version": 1,
  "exported_at": "2026-09-25T14:30:22Z",
  "source_username": "jdoe",
  "architectures": [ { "...": "each item validated individually server-side" } ]
}
```

`architectures` is typed as `list[dict[str, Any]]`, so one malformed entry can't fail the whole request (research §8). `exported_at` and `source_username` are optional on import.

**Responses**:

| Status | Body | When |
|---|---|---|
| `200` | `ArchitectureImportResponse` | The envelope is valid. Includes files where every entry failed, and an empty `architectures` list. |
| `400` | `{"error": "invalid_import_file", "message": "<reason>"}` | Wrong `format`, unsupported `format_version`, or `architectures` missing or not a list (FR-019). Nothing is written. |
| `422` | FastAPI validation error | The body isn't a JSON object. The client treats this the same as `400`, as "Import failed". |
| `404` | — | `user_id` is unknown or is a guest. |

```json
{
  "imported_count": 1,
  "failed_count": 2,
  "results": [
    { "name": "Web App",   "status": "success", "error": null },
    { "name": "Data Lake", "status": "failed",  "error": "Architecture name already exists" },
    { "name": "Legacy",    "status": "failed",  "error": "Service not found in pricing data: AmazonXYZ / ABC123 (us-east-1)" }
  ]
}
```

- `results` follows the file's order, one item per `architectures[]` entry.
- `name` is `null` when an entry has no readable name. The UI shows "(unnamed #n)".
- Each successful entry is committed on its own, with all-or-nothing writes per architecture (research §9).
- Imported architectures are owned by `user_id` with `is_public = false` (FR-023).

**Pricing-data outage**: if DuckDB is unreachable during SKU validation, the existing `PricingDataUnavailableError` handler returns `503`, and nothing from the file is written. That check runs before any insert.

---

## Frontend client additions (`frontend/src/api/client.ts`)

```ts
exportUserArchitectures: (userId: string) =>
  request<ArchitectureExportFile>(`/admin/users/${userId}/architectures/export`),
importUserArchitectures: (userId: string, doc: unknown) =>
  request<ArchitectureImportResponse>(`/admin/users/${userId}/architectures/import`, {
    method: "POST", body: JSON.stringify(doc),
  }),
```

The type aliases come from `components["schemas"]` like the existing `AdminUser`.
