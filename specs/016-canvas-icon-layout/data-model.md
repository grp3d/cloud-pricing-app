# Data Model: Canvas Icon Layout, Active Pricing Snapshot & Configurable Settings

This feature adds **no Postgres tables or columns**. The one database change is behavioral:
`sku_selections.collection_id` can now change when a service is moved to another box. Everything
else is in-memory backend state, a generated JSON file, or browser `localStorage`.

---

## 1. Active Snapshot State (backend, in memory)

`backend/src/pricing_data/active_snapshot.py` has one module-level instance, rebuilt on every
restart (spec Clarification Q4).

| Field | Type | Notes |
|---|---|---|
| `active_date` | `date \| None` | The date every pricing lookup uses (FR-014). `None` only if no complete date exists and no override is set. Lookups then raise `PricingDataUnavailableError`, which maps to 503. |
| `pinned` | `bool` | True when `settings.active_snapshot_date` is set (FR-018). |
| `last_check_at` | `datetime \| None` | UTC time the most recent check finished. |
| `last_check_error` | `str \| None` | Why the most recent check failed, e.g. an unreadable folder. It is cleared by the next successful check. |
| `waiting` | `list[WaitingSnapshot]` | Dates newer than `active_date` that are not complete. |
| `marker_mtimes` | `dict[str, float]` | Table → `_SUCCESS` modification time for `active_date`. A change triggers re-analysis (FR-023). |
| `issues` | `list[Issue]` | The current Issues table (FR-022). |

**WaitingSnapshot**: `{ date: date, reason: str }`. Example reasons:
- `"missing from price_fact"`
- `"no completion marker in product_dim, region_dim"`

### Completeness rule

A date *D* is **complete** when `<table>/snapshot_date=<D>/_SUCCESS` exists for all five tables:
service_dim, product_dim, product_attribute, region_dim and price_fact.

### Check behavior (one run)

```text
                 ┌─ override set? ──yes─▶ active = override (validated at startup; never switched)
check ──scan──▶  │                        waiting / marker times / issues still refreshed
                 └─ no ─▶ newest complete date C
                           C > active?  ──yes─▶ switch: active = C
                                                  ├─ running switch (not startup): compare regions → region issue(s)
                                                  └─ run icon analysis
                           C == active and marker times changed? ──▶ run icon analysis
                           otherwise ──▶ no analysis (FR-023)
                 scan error ──▶ keep active; last_check_error set; retry next interval
```

### Startup validation (FR-017/FR-018/FR-026)

- **Override set**: the date's folder must exist in all five tables, or startup fails with a
  message naming `ACTIVE_SNAPSHOT_DATE`. If the date exists everywhere but lacks markers, it is
  accepted and a `pinned_incomplete` issue is recorded.
- **No override**: `active_date` is the newest complete date. If there is none, `active_date` is
  `None` and `last_check_error` explains why.

## 2. Issue (backend, in memory)

| Field | Type | Present for |
|---|---|---|
| `kind` | `"missing_icon" \| "missing_regions" \| "pinned_incomplete"` | all |
| `snapshot_date` | `date` | all |
| `service_code` | `str` | missing_icon |
| `service_name` | `str \| None` | missing_icon (read from service_dim) |
| `is_new` | `bool` | missing_icon: true when the code is absent from the next-older date present in all tables |
| `regions` | `list[str]` | missing_regions: regions present in the previously active date but not the new one |
| `message` | `str` | all; a one-line human-readable summary |

### Lifecycle

- **`missing_icon`**: replaced wholesale on each icon analysis (at startup, on a switch, or when
  the markers change). A service that can now be matched disappears on the next analysis
  (FR-024).
- **`missing_regions`**: added only when the date switches while the server is running (FR-016).
  It is kept until the next switch, and lost on restart.
- **`pinned_incomplete`**: present while pinned to a date without markers.

**Ordering**: `pinned_incomplete`, then `missing_regions`, then `missing_icon`. Within
`missing_icon`, new services come first, then by service code.

## 3. AWS Service Icon Map, backend copy (generated)

`backend/src/pricing_data/aws_service_icons.json` is written by
`backend/scripts/generate_aws_service_icon_map.py` in the same run as the frontend's
`awsServiceIcons.generated.ts`, and holds the same content:

```json
{
  "by_code": { "AmazonDynamoDB": "Amazon-DynamoDB", "...": "..." },
  "by_code_and_family": { "AmazonEC2": { "NAT Gateway": "Amazon-Virtual-Private-Cloud" } },
  "special_codes": ["AWSDataTransfer"]
}
```

**Matching rule** (the same as `resolveAwsServiceIcon`, ignoring product family): a service code
has an icon if it is in `by_code` or `special_codes`.

**Validation**: a test asserts that `by_code`, `by_code_and_family` and `special_codes` are
identical to the TS maps.

## 4. SKU Selection, move between boxes (Postgres, existing table)

The table is unchanged. `PATCH /sku-selections/{id}` accepts an optional `collection_id`
(contracts/api.md). When it is present:

| Rule | Failure |
|---|---|
| The selection is collection-owned (it has `collection_id`, not `connector_id`) | 400 `not_movable` |
| The target collection exists, is not deleted, and is in the same architecture, which the user owns | 404 |
| `target.region == source.region` | 409 `region_mismatch` |

**On success**: `selection.collection_id = target.id`. Pricing inputs are unchanged. The target
collection becomes region-locked if it wasn't already (010 FR-003, which is derived from its
content). The source collection may become unlocked if it's now empty.

## 5. Icon Position (frontend, per browser)

`localStorage` key: `cloud-pricing-icon-layout-<architectureId>`

```ts
type IconLayout = Record<string /* skuSelectionId */, { x: number; y: number }>;
```

- `x` and `y` are in canvas units, relative to the top-left of the box's icon area.
- A missing entry means default placement (FR-008).
- An invalid entry, whether malformed or no longer satisfying the spacing rule, is ignored and
  replaced by the first free default slot.
- Moving a service to another box keeps its key; the position is then read relative to the new
  box (and re-validated there).
- **Constraint**: two icons in the same box are always separated by at least `GAP` (60) on the x
  axis or on the y axis. So their squares never overlap, and no two are closer than one icon
  width.

## 6. Layout constants (frontend)

| Name | Value | Source |
|---|---|---|
| `ICON` | 60 | FR-001 (2.5 × 24) |
| `GAP` | 60 | Clarification (one icon width; reduced from 90 after review) |
| `MAX_PER_ROW` | 3 | Clarification (boxes widen to fit 3 icons: 320px) |
| `PAD` | 8 | the box's existing `p-2` |
| `LABEL_RESERVE` | 16 | room for the box's region label (015) |

Default top-level box slots (research.md §11a): left to right by real width, 4 per row, with
80px between boxes and 40px between rows (each row below the tallest box of the previous one).
Saved positions override the slot.

Default box width = max(today's default, `2*PAD + n*ICON + (n-1)*GAP + borders`), where
n = min(icons, 3). For 3 icons that's 316 + borders = 320.

## 7. Settings (backend configuration)

All fields live on `Settings` in `src/config.py`. The environment variable is the upper-cased
field name. Every default equals today's behavior.

| Field | Env var | Type | Default | Validation |
|---|---|---|---|---|
| `database_url` | `DATABASE_URL` | str | `postgresql+psycopg://localhost/cloud_pricing_dev` | existing |
| `aws_pricing_parquet_dir` | `AWS_PRICING_PARQUET_DIR` | str | the current local path | existing |
| `aws_pricing_region` | `AWS_PRICING_REGION` | str | `us-east-1` | existing |
| `cors_allowed_origins` | `CORS_ALLOWED_ORIGINS` | list[str] (JSON) | `["http://localhost:5173"]` | non-empty |
| `catalog_search_default_limit` | `CATALOG_SEARCH_DEFAULT_LIMIT` | int | 50 | ≥ 1, ≤ max |
| `catalog_search_max_limit` | `CATALOG_SEARCH_MAX_LIMIT` | int | 200 | ≥ 1 |
| `password_hash_iterations` | `PASSWORD_HASH_ITERATIONS` | int | 260000 | ≥ 100000 |
| `log_level` | `LOG_LEVEL` | str | `INFO` | one of DEBUG, INFO, WARNING, ERROR |
| `snapshot_check_interval_seconds` | `SNAPSHOT_CHECK_INTERVAL_SECONDS` | int | 300 | ≥ 10 |
| `active_snapshot_date` | `ACTIVE_SNAPSHOT_DATE` | date \| None | None | ISO date; existence is checked at startup |
