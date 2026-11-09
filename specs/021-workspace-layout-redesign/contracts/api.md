# API Contract Changes (021)

There are two additive, backward-compatible changes. No route is added or removed, and no
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
