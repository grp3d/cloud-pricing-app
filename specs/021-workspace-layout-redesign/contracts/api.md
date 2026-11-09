# API Contract Changes (021)

There are four additive, backward-compatible changes. No route is added or removed, and no
response shape changes beyond the new optional field. The frontend types are regenerated
from OpenAPI (`npm run generate-api-types`), and CI's `api-contract-drift` job fails on
drift (constitution IV).

## 1. `GET` / `PATCH /api/v1/me/preferences`: `workspace.inspector`

`WorkspacePreferences` gains one optional field:

```text
workspace:
  column_widths?: { col1..col4: int > 0 }       # unchanged; 021 reads col2 and col4
  collapsed?:     { col1..col4: bool }          # unchanged; 021 reads col2 and col4
  last_provider?: "aws" | "gcp" | "azure"       # unchanged
  inspector?:                                   # NEW (021)
    mode:  "merged" | "split"
    upper: "pricing" | "service"
    front: "pricing" | "service"
    split: number, 0.2 ≤ split ≤ 0.8
```

**Rules**:
- **PATCH replaces the whole `workspace` section,** as today (`patch_preferences`, "a write
  replaces whole sections"). So the frontend always sends the current `workspace` object with
  the changed field, as `columnWidths.ts` already does.
- **`inspector`, when present,** must have all four fields. A missing field, an unknown
  value, `split` outside [0.2, 0.8], or an unknown key each return **422** with no change
  stored.
- **`inspector` absent** means the default: merged, Pricing upper and front, split 0.5.
- **`schema_version` stays 1.** Existing rows validate unchanged.

**Tests, written first in `backend/tests/contract/test_preferences.py`**:
1. PATCH with a valid `inspector`, then GET, returns it unchanged.
2. PATCH with an `inspector` whose `split` is 0.1 returns 422, and the previous value is
   still stored.
3. PATCH with `mode: "tabs"`, or an extra key, returns 422.
4. PATCH that replaces `workspace` without `inspector` removes the stored `inspector`, the
   same section-replace rule as the other fields.
5. A row stored before 021 (no `inspector`) still reads back.

## 2. `GET /api/v1/architectures/importable?provider=`

There is a new optional query parameter, `provider`, which takes `aws`, `gcp` or `azure`.

- **With `provider`:** only that provider's public architectures of other users are
  returned. Grouping and order are as today: Admin first, then owners alphabetically, then
  names alphabetically within an owner. An owner with none for that provider is left out.
- **Without `provider`:** exactly today's response, with every provider.
- **Unknown provider:** returns 422, the same validation as other provider parameters.
- **The response shape is unchanged** (`ImportableArchitecturesOut`).

**Tests, written first**:
1. With public AWS and GCP architectures from another user, `?provider=gcp` returns only the
   GCP ones.
2. With no parameter, both are returned (today's behaviour).
3. `?provider=gcp` with no GCP public architectures returns `{ groups: [] }`.

**Frontend**:
- `api.listImportableArchitectures(provider?: ProviderCode)` appends `?provider=` when it is
  given.
- The query key is `["importableArchitectures", provider]`.

## 3. `PATCH /api/v1/architectures/{id}`: rename (US6, FR-043)

The owner-only update that toggled `is_public` (012) also takes a `name`. Both fields are
optional; only those sent change, and at least one is required.

```json
{ "name": "Shop Front" }
```

- `name` is trimmed; a blank name, or one over 255 characters, returns 422 and leaves the
  stored name unchanged. An empty body returns 422.
- Guests may rename their own architectures (only `is_public: true` is refused for them,
  as before).
- Not the owner, or deleted: 404, as before. The response is the architecture summary, as
  before.

Contract tests (`backend/tests/contract/test_architecture_sharing.py`): rename keeps
`is_public`; not-owner 404; a guest renames their own; `{}`, `""`, `"   "` and 256 characters
each return 422 with the name unchanged.

## 4. `SKUSelectionOut.summary` (US7, FR-044)

Every saved service in `GET /architectures/{id}` (and the create and update responses) gains
an optional `summary: string | null`: the item's own description, as the catalog search shows
it, from the provider adapter's `describe` at response time (never stored).

- GCP: the SKU's display name, e.g. "Multi-Region HNS Nearline Class A Operations".
- Azure: product, SKU and meter names joined, as in the search, leaving out any word an
  earlier name already has ("Premium SSD Managed Disks P10 LRS Disk", not "… P10 LRS P10 LRS
  Disk"). The catalog search's `summary` reads the same, since both come from one function.
- AWS: always null (the AWS `describe` leaves it empty; AWS's readable details stay in
  `attributes`). `service_name` stays null for AWS too, as in 020.

Contract tests (`backend/tests/contract/test_architectures.py`): GCP and Azure selections
carry a non-blank summary that isn't the service code; an AWS selection's is null.

