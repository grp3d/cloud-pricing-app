# Data Model: GCP and Azure Providers, Trends Page, Saved Preferences and Diagram Arrows

**Feature**: `019-gcp-azure-providers-trends` | **Date**: 2026-11-02 | **Research**: [research.md](./research.md)

Three kinds of data, kept apart as Principle II requires:

1. **Postgres (user-defined data, written by the app)**: §1 to §5.
2. **Vendor pricing data (read-only Parquet, per provider)**: §6, reference only; owned by the pipeline.
3. **Derived price history (rebuildable local files, never in Postgres)**: §7.

Migration `0006_providers_trends_preferences` adds every schema change; `0007_service_category_seed` loads the category seed (§2).

---

## 1. `user_preferences` (new)

One row per user (named or guest).

| Column | Type | Rules |
|---|---|---|
| `user_id` | UUID, PK, FK → `users.id` ON DELETE CASCADE | One row per user. Deleted with a guest identity. |
| `data` | JSONB, not null, default `{}` | Must validate against `Preferences` (below) |
| `schema_version` | int, not null, default 1 | Bumped when `Preferences` changes incompatibly |
| `updated_at` | timestamptz | Set on every write |

`Preferences` (Pydantic, mirrored in TypeScript; unknown keys rejected):

```text
Preferences
├── migrated_from_browser: bool = false
├── workspace?:  { column_widths?: {col1?, col2?, col3?, col4?: int px},
│                  collapsed?: {col1?, col2?, col3?, col4?: bool},
│                  last_provider?: "aws" | "gcp" | "azure" }
└── trends?:
    ├── charts?: { providers: [{provider, regions: [string]}],   # empty regions = all regions
    │              category: "all" | "compute" | "storage" | "database" | "networking" }
    └── movers?: { provider, category, regions: [string], period_weeks: 1 | 4 | 13 | 52 }
```

- **Writes**: a PATCH replaces whole top-level sections (`workspace`, `trends.charts`, `trends.movers`). The last write wins per section (R12).
- **Missing data**: an empty or missing section means "use the defaults" (spec FR-020).
- **Stale stored values**: a region or provider no longer available is dropped when the page loads, and the cleaned value is saved back.

## 2. `service_category_rules` (new, seeded)

This maps provider groupings to shared categories (R9).

| Column | Type | Rules |
|---|---|---|
| `id` | UUID PK | |
| `provider` | varchar(20) | `aws`, `gcp`, `azure` |
| `match_field` | varchar(40) | AWS: `service_code`, `product_family`. Azure: `service_family`, `service_name`. GCP: `taxonomy_1`, `taxonomy_2` |
| `match_value` | varchar(255) | Exact, case-sensitive value as published |
| `category` | varchar(20) | `compute`, `storage`, `database`, `networking` (CHECK) |
| `priority` | int | Higher wins when several rules match |

- **Unique key**: (`provider`, `match_field`, `match_value`).
- **No match**: the item is uncategorized, so it shows only under "all categories" and never in a category's movers (FR-017).
- **Seeding**: from `backend/src/db/seed/service_categories.json`, idempotent like the standard architectures seed.

## 3. `sku_selections` (changed)

| Change | Detail |
|---|---|
| `pricing_term` CHECK widened | Adds `savings_plan_1yr`, `savings_plan_3yr`, `commitment_1yr`, `commitment_3yr` (R6) |
| `provider_options` JSONB, nullable (new) | A discriminated union on `kind`: `gcp_machine` `{version, vcpus > 0, memory_gib > 0, ram_sku}` or `azure_vm` `{version, os: linux \| windows}`. Null means the common pricing path. |
| `service_code`, `sku` meaning per provider | AWS unchanged. Azure: `service_id`, `<sku_id>/<meter_id>`. GCP: `service_id`, `sku_id` (R4). |

Validation is done in the service layer, because it depends on the architecture's provider:

- A price type must be one the provider supports (R6 table) and one the item publishes.
- `purchase_option` is `not_applicable` for Azure and GCP.
- `provider_options.kind` must belong to the architecture's provider.

## 4. `collections` (changed)

| Change | Detail |
|---|---|
| `region` widened from varchar(20) to varchar(64) | Fits GCP and Azure location names (R5) |

The region is validated against `GET /regions?provider=<architecture provider>`.

## 5. `data_connectors` (changed) and `connector_branches` (new)

`data_connectors` gains:

| Column | Type | Rules |
|---|---|---|
| `arrow_style` | varchar(20), not null, default `none` | CHECK in (`none`, `one_way`, `two_way`, `one_to_many`, `many_to_one`) |
| `arrow_reversed` | bool, not null, default false | Visual only; meaningful only for `one_way`, `one_to_many` and `many_to_one` |

`connector_branches` (new):

| Column | Type | Rules |
|---|---|---|
| `id` | UUID PK | |
| `connector_id` | UUID FK → `data_connectors.id` ON DELETE CASCADE | |
| `collection_id` | UUID FK → `collections.id` | Same architecture as the connector (service layer). Not the connector's own `from`/`to`, and not a duplicate. |
| `created_at` | timestamptz | Branch display order |

Rules:

- **Where branches are allowed**: rows exist only when `arrow_style` is `one_to_many` (extra "to" boxes) or `many_to_one` (extra "from" boxes).
- **Changing the style**: changing to any other style needs the branches removed first. The service layer refuses with a clear message.
- **Lifecycle when a box is deleted**:
  - A branch box is deleted: its branch row is removed.
  - The connector then has 2 boxes: `arrow_style` becomes `one_way`.
  - The primary `from` or `to` box is deleted: the oldest branch box is promoted into its place. If none is left, the connector is soft-deleted as today.
- **Pricing**: the optional data transfer `sku_selection` stays one per connector and is priced from `from_collection.region` (FR-027a).

## 6. Vendor pricing data (read-only, per provider)

These tables are owned by the pipeline and defined in `../cloud-pricing-data-retrieval/specs/004-add-azure-gcp-pricing/data-model.md`. What the app relies on:

| Provider | Tables | Item key used here | Price columns | Tier columns | Grouping for categories |
|---|---|---|---|---|---|
| AWS | 5 tables, unchanged | `sku` | `price_fact.price` | `begin_range`, `end_range` (text; `Inf` = open top tier) | `service_code`, `product_family` |
| Azure | `price_item`, `price_item_savings_plan` | `sku_id/meter_id` | `unit_price` (nullable) | `tier_minimum_units` | `service_family`, `service_name` |
| GCP | `service`, `sku`, `sku_price`, `sku_price_tier` | `sku_id` | `sku_price_tier.list_price` (decimal; nullable) | `start_amount` | `product_taxonomy[1..2]` |

- **Null prices**: a null price means "not published", never zero (FR-007).
- **Tiers**: every adapter turns its tier columns into an ordered `(start_quantity, rate)` list for the shared graduated-tier function (research R8).
- **Reading a region L**: always read L plus `global`.
- **Snapshots in use**: one snapshot per provider per request, taken once at the start (as in 018).

## 7. Derived price history (local files, rebuildable)

Location: `PRICING_HISTORY_DIR/<provider>/` (default `~/.cloud-pricing/history`, persistent, outside the snapshot cache and its size limit). It is not in Postgres and not backed up. A missing or corrupt history is rebuilt from the snapshots (R10).

| File | Rows | Columns |
|---|---|---|
| `prices/<date>-r<rev>.parquet` (newest only) | One per comparable item per location | `location`, `item_key`, `service_key`, `description`, `unit`, `price` (first non-zero tier, on-demand) |
| `pairs/<from_date>_<to_date>/changes.parquet` | One per item whose price changed | `location`, `item_key`, `service_key`, `description`, `unit`, `old_price`, `new_price` |
| `pairs/<from_date>_<to_date>/counts.parquet` | One per (`location`, `service_key`) | `compared`, `unchanged`, `increased`, `decreased`, `added`, `removed`, `excluded` |
| `pairs/<from_date>_<to_date>/pair.json` | One | from/to `snapshot_date` + `revision`, `built_at`, builder version |
| `state.json` | One | weeks built, gaps (missing or purged weeks), last error, backfill progress |

Rules:

- **Week pairs**: snapshots are grouped by ISO week, and the latest non-purged snapshot (latest revision) in each week represents that week; other snapshots in the week are ignored. Pairs are consecutive weeks. A missing week is a gap; the pair spans it, and the chart marks that point.
- **Comparable price**: only a valid, non-zero price at both ends counts as compared. A missing or zero price at either end is excluded. Items present at only one end are added or removed.
- **Rebuilds**: a new revision of a built date rebuilds the pairs on either side. A builder version change rebuilds everything.

## 8. Computed (not stored) values

| Value | From | Definition |
|---|---|---|
| Trend point (SKUs Changed) | `counts` for the selected locations and service keys | increased, decreased, compared, excluded; increased ÷ compared and decreased ÷ compared as % (R11) |
| Price mover | `changes` across the window's pairs | Per (`location`, `item_key`): first `old_price`, last `new_price`, % change. Net-zero changes and items removed before the end are dropped. |
| Provider status | Per-provider `MonitorState` | `current` / `partial` / `failed` / `stale` / `none`, plus a reason |
