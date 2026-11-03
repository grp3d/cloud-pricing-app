# Research: GCP and Azure Providers, Trends Page, Saved Preferences and Diagram Arrows

**Feature**: `019-gcp-azure-providers-trends` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

Sources read: the app's backend (`backend/src/pricing_data/*`, `services/price_calculation.py`, `models/orm.py`, `models/schemas.py`) and frontend (`frontend/src/**`), and the pipeline's feature 004 contracts (`../cloud-pricing-data-retrieval/specs/004-add-azure-gcp-pricing/`: `contracts/app-note.md`, `contracts/storage-layout.md`, `data-model.md`, `checklists/validation.md`).

---

## R1. One snapshot monitor per provider

**Decision**: Generalize `active_snapshot.py` from one hard-coded `PROVIDER = "aws"` to one `MonitorState` per provider, keyed by provider code. Each provider gets its own `latest.json` pointer, manifest validation, active snapshot, latest-run, rejection and issue list. `get_active_snapshot(provider)` replaces the no-argument form; the AWS-only callers pass `"aws"` until they move behind the provider adapters (R3). One background check loop visits the three providers in turn. A failure in one provider is recorded in that provider's state only (spec FR-002, app note point 1).

`manifest.py` gets a per-provider table registry, replacing the single `TABLES` tuple:

| Provider | Tables (schema version 1) |
|---|---|
| `aws` | `service_dim`, `product_dim`, `product_attribute`, `region_dim`, `price_fact` |
| `azure` | `price_item`, `price_item_savings_plan` |
| `gcp` | `service`, `sku`, `sku_price`, `sku_price_tier` |

Validation rejects an unknown table name or `schema_version` per provider (storage-layout contract). The file-path check accepts location names (`^[a-z0-9]+(-[a-z0-9]+)*$`), not only AWS region codes. The manifest models accept the optional 1.1 fields (`catalog`, `excluded_price_types`, `run.region_results`) by ignoring them, as they already do (`extra="ignore"`). The vendored contract fixtures move to the 1.1 schemas.

`ActiveSnapshot.common_regions()` (regions present in every table) doesn't work for GCP, whose `service` table has files only in `global`. It becomes provider-specific: `locations()` returns the manifest's `regions.succeeded`, and each provider adapter decides which of those are selectable regions (R5).

**Rationale**: The app note asks for exactly this. Keeping one state per provider keeps today's AWS behavior and tests intact: the AWS state is the old global state under a key.

**Alternatives considered**: Three separate background tasks were rejected because they triple the timers and locks for no gain, since the checks are short. One combined "all providers" snapshot was rejected because it would let one provider's failure block the others (FR-002).

## R2. Cache budget for three active snapshots

**Decision**: Keep the existing verified S3 cache (`snapshot_cache.py`), already keyed by provider in `list_entries`. Its clean-up becomes provider-aware: each provider's active snapshot is protected, `pricing_cache_keep` applies per provider, and the size budget (`PRICING_CACHE_MAX_BYTES`) is shared. Measuring the real snapshot sizes is an early task. Azure and GCP are small (validation Q1 and Q2: about 33k and 18k rows per location). If AWS plus both fit under 1 GiB, the default stays; otherwise the default rises with the instance disk in `infra/`.

**Rationale**: It reuses the integrity rules feature 018 established (sha256-verified files, a snapshot never mixes revisions) with no new mechanism.

## R3. A shared request shape with provider adapters behind it (FR-006, Principle III)

**Decision**: Add a `PricingProvider` protocol in `backend/src/pricing_data/providers/`, with one implementation per provider (`aws.py`, `azure.py`, `gcp.py`) and a registry `get_provider(code)`. The protocol's methods are the common operations the screens use:

- `locations(snapshot)`: the selectable regions.
- `search(snapshot, query)`: catalog search returning `CatalogItem`s.
- `describe(snapshot, refs, region)`: attributes, unit and group for stored selections.
- `exists(snapshot, refs, region)`: used by import validation.
- `price(snapshot, selection, region)`: a `PriceQuote` covering recurring rate, upfront fee, unit, tiers and price type.
- `service_key(item)`: the key that service categories match on (R9).
- `comparable_prices(snapshot)`: the on-demand price list used by the trend builder (R10).

The AWS adapter wraps today's functions (`search_catalog`, `resolve_units`, `lookup_price`, `lookup_reserved_price`, `resolve_product_details`, `find_existing_skus`) without changing their behavior, with one deliberate exception: on-demand prices with tiers are now applied by tier (R8). All other AWS tests keep passing unchanged, which is the regression guard. Tests whose expected totals came from the old single-tier lookup are updated, and each change is listed in the tasks.

Every existing endpoint keeps its path and shape and gains a `provider` value: a query parameter for catalog and regions, and the architecture's own `provider` for selections and calculation. A request with no provider means `aws`, so the frontend can migrate gradually and old clients still work. Provider-specific fields travel in one typed, discriminated `provider_options` object (R6).

**Rationale**: This matches the app note's suggested work and constitution v1.1.0 Principle III. One adapter per provider keeps each provider's oddities in one tested place: AWS data transfer region attributes, Azure text filters, GCP composite machines.

**Alternatives considered**: Separate endpoints per provider (`/azure/catalog`) were rejected by FR-006. Reshaping Azure and GCP data into AWS's five tables was rejected because Principle III says normalization happens in the app, and it would hide the source shape.

## R4. How a selection refers to a GCP or Azure price

**Decision**: Keep `sku_selections.service_code` + `sku` as the stored reference and fill them per provider:

| Provider | `service_code` | `sku` | Why that is stable |
|---|---|---|---|
| AWS | `service_code` (unchanged) | `sku` (unchanged) | — |
| Azure | `service_id` | `<sku_id>/<meter_id>` | One meter of one Azure SKU. `price_type` and reservation term are chosen by the price type (R6), not stored in the reference. |
| GCP | `service_id` | `sku_id` | The GCP SKU. Its consumption models (Default, CUDs) are chosen by the price type. |

Lookups always filter by the selection's region plus `global` (R5). The import validation (`exists`) and catalog details use the same key.

**Rationale**: No schema change is needed to the reference columns, which are 100 characters wide; the Azure key is about 55. References use stable source identifiers, not copied attributes (Principle II).

**Alternatives considered**: Azure `price_item_key` was rejected because it is a content hash, so it changes whenever the price changes and can't identify the same item from week to week. Azure `product_id` + `sku_id` was rejected because one SKU can have several meters, such as disk capacity and disk operations.

## R5. Locations, `global` and multi-regional SKUs

**Decision**:

- **Selectable regions**: Azure and GCP regions come from `regions.succeeded`, excluding `global`. Azure geography locations such as `north-america` are excluded too; they hold only Bandwidth Alliance and inter-region prices (storage-layout). Each region shows its source display name (Azure `location_display_name`).
- **Pricing and search in region L**: read L's files plus `global`'s (contract rule). Results from `global` are labeled "global" (spec edge case).
- **GCP multi-regional SKUs** are filed under each member region, so within one region a SKU appears once. Trend and mover counts work per region, and the same SKU in two selected regions counts once per region (spec edge case). Counting distinct SKUs across a region set uses `(location, sku_id)` pairs.
- **Data transfer on connectors**: the connector's "from" region is used, as for AWS. Azure egress is read from the region partition (`Bandwidth`, `Rtn Preference: MGN` or `…Internet`, per the contract); GCP egress from the `Network > Egress` taxonomy.
- **Width**: `collections.region` widens from 20 to 64 characters. GCP names such as `northamerica-northeast1` are 23.

## R6. Price types, Service Editor fields and GCP machines (FR-005, FR-005a)

**Decision**: Extend the price types with an enum shared across providers and keep the existing AWS values:

| `pricing_term` | AWS | Azure | GCP |
|---|---|---|---|
| `on_demand` | OnDemand | `price_type = 'Consumption'` | `consumption_model_description = 'Default'` |
| `reserved_1yr` / `reserved_3yr` | Reserved (+ `purchase_option`) | `Reservation`, `reservation_term` `1 Year` / `3 Years` | — |
| `savings_plan_1yr` / `savings_plan_3yr` (new) | — | `price_item_savings_plan.term` | — |
| `commitment_1yr` / `commitment_3yr` (new) | — | — | CUD prices (`… CUD - 1 Year` / `- 3 Year`) |

`purchase_option` stays `not_applicable` for Azure and GCP. The adapter reports which price types each item actually publishes, and the Service Editor offers only those (FR-005).

**Azure reservation**: the source gives `unitPrice` as the total for the term. It is priced like AWS all-upfront: an upfront fee and no recurring rate, reusing the existing calculation path. The editor shows it as a term price.

**`provider_options`** is a new nullable, typed JSON column on `sku_selections`. It is a discriminated union validated by Pydantic, mirrored in TypeScript, and carries a version number (Principle IV):

- `gcp_machine`: `{kind: "gcp_machine", version: 1, vcpus, memory_gib, ram_sku}`. The stored `sku` is the core SKU, and `ram_sku` is the matching RAM SKU. The price is vCPUs × core rate + GiB × RAM rate, computed by the GCP adapter as the contract documents. The parts are shown in the line-item detail.
- `azure_vm`: `{kind: "azure_vm", version: 1, os: "linux" | "windows"}`. It picks the Windows or non-Windows meter, using the contract's text filters.
- Absent for the common path, where any SKU is priced with price type, unit and quantity.

The other core kinds (block storage, object storage, data transfer, managed databases) need no extra stored fields. Their tuning is in search presets and editor labels: the adapter supplies a `kind` hint on catalog items, using the reference lookup filters.

**Rationale**: It covers whole-catalog pricing with common fields (clarification Q2) and adds only the two stored options the reference lookups need.

**Alternatives considered**: Storing the GCP machine as two separate selections was rejected because users think of it as one machine, and editing two lines in step is error-prone.

## R7. Units and quantities

**Decision**: Each adapter turns its source unit into the existing `UnitClassification` (`duration.py`: `no_period`, `fixed_period`, `unrecognized`) through its own explicit table, mirroring the AWS table's style:

- **Azure** `unit_of_measure` carries a multiplier and a base, such as `1 Hour`, `1 GB/Month`, `10K` or `1/Month`. It is parsed into (multiplier, base) by a small table of known forms. An unknown form is `unrecognized`, so the line is reported unpriceable, never guessed (FR-007, Principle I).
- **GCP** `unit` (`h`, `GiBy.mo`, `GiBy`, `count`, …) with `unit_quantity` gives the price per `unit_quantity` units. Cost is price × quantity ÷ `unit_quantity`.

The editor shows the unit as published and the quantity in that unit (FR-005).

## R8. Tiered prices

**Finding**: AWS publishes tiers as separate `price_fact` rows with `begin_range` and `end_range`, but `lookup_price` reads one row with an unsorted `LIMIT 1`, so a tiered SKU is priced at whichever tier comes back first. In the 2026-09-21 us-west-2 snapshot, 308 of 171,304 on-demand price keys are tiered, mostly internet data transfer (for example $0.09, $0.085, $0.07 and $0.05 per GB for the first 10 TB, next 40 TB, next 100 TB and above 150 TB), S3, CloudWatch, SES and the AI services. Taking the first tier for Azure would be wrong too: its data transfer first tier is the free 100 GB (price 0), so every egress line would be $0.

**Decision** (spec FR-008, clarification 2026-11-03): **graduated tiers for all three providers**, through one shared function.

- **Per adapter**: each adapter converts its own columns into an ordered list of `(start_quantity, rate)`:
  - AWS: `begin_range` / `end_range` (text; `Inf` is the open top tier), all rows of the same SKU, term and options.
  - Azure: `tier_minimum_units`; each tier ends where the next one starts.
  - GCP: `sku_price_tier.start_amount`.
- **Shared**: `apply_tiers(tiers, quantity)` splits the quantity across the tiers and prices each part at its own rate. For tiers 0–10, 10–20 and 20–1000 and a quantity of 40: 10 × tier 1 + 10 × tier 2 + 20 × tier 3. It returns the parts for the line item's `tiers` breakdown. A single-tier price is the same calculation with one part, so non-tiered SKUs get identical results.
- **Tier period**: published tiers are per month. The line's quantity is converted to a monthly quantity using the app's fixed 31-day month (`_DURATION_DAYS`), tiered, and the tiered cost is then scaled to the requested duration. The conversion follows today's unit classes (`classify_unit`):

  | Unit class | Meaning of the entered quantity | Monthly quantity for tiering | Cost for the duration |
  |---|---|---|---|
  | No period (hours, GB transferred, requests, …) | A steady daily amount | quantity × 31 | tiered monthly cost × duration days ÷ 31 |
  | Fixed period of *d* days (for example GB-Mo) | An amount held over the unit's own period | quantity as entered | tiered cost × duration days ÷ *d* |
  | Unrecognized | — | — | Line is unavailable, as today (FR-007) |

  For a single-tier price both rows give exactly today's result.
- **Per line**: tiers apply to each line on its own, not pooled across lines or across the account (spec Assumptions).
- **Free allowances**: applied only when published as a tier (Azure's free 100 GB is; AWS's account-wide 100 GB is not in the data).
- **Quantity above the top tier**: if the top tier has an upper bound and the quantity goes past it, the excess is priced at the rate of the tier with the highest upper bound. In the current data every top tier is open-ended (AWS `end_range` is `Inf`; Azure and GCP publish only tier starts), so this is a safeguard.
- **Duplicate tier rows**: Azure lists some meters under several meter names with the same tier start and the same price (31 items in the 2026-11-02 snapshot). They collapse to one tier. If such rows ever had different prices, the line is unpriceable, because the right rate can't be told.
- **Null tier price**: none in the current data for any provider. If one appears in a tier the quantity reaches, the line is unpriceable ("not published"), never partly priced (FR-007).
- **Checked on local data**: AWS 2026-09-21 (1,887 tiered keys across regions), Azure 2026-11-02 (1,021 tiered items) and GCP 2026-11-02 (2,595 tiered SKUs): no gaps between tiers, no null tier prices, every first tier starts at 0, and every top tier is open-ended.
- **AWS impact**: existing AWS architectures with tiered prices can show a different, correct total. Affected tests are updated deliberately (R3).

For trends and movers, a tiered item is compared on its **first non-zero tier**, so a free tier doesn't hide price changes. That is stated in the hover detail and the movers entry (spec edge case).

## R9. Service categories (FR-015a, FR-017)

**Decision**: A Postgres table `service_category_rules` maps provider groupings to the four shared categories. The constitution (Principle II) places linking and mapping tables to internal categorizations in Postgres. It is seeded by a migration, with editing left to later features. Rules match per provider:

| Provider | Field matched | Examples |
|---|---|---|
| AWS | `service_code` (optionally `product_family`) | `AmazonEC2` + `Compute Instance` → compute; `AmazonS3` → storage; `AmazonRDS` → database; `AWSDataTransfer` → networking |
| Azure | `service_family`, then `service_name` | `Compute` → compute; `Storage` → storage; `Databases` → database; `Networking` → networking |
| GCP | `product_taxonomy[1]`, then `[2]` | `Compute` → compute; `Storage` → storage; `Databases` → database; `Network` → networking |

The rule with the highest priority wins, and no matching rule means uncategorized (FR-017). Trend data stores each item's **service key**, not its category. Categories are applied when a query runs, so a rule change takes effect immediately with no rebuild.

## R10. Price history for Trends (FR-012 to FR-019)

**Finding**: Retention keeps weekly snapshots for 12 months and then one per month (pipeline 003 FR-021), so 52 weeks of history exist in storage for AWS. Azure and GCP start at their first production snapshot. Their production rollout (pipeline 004 quickstart Part C, steps C2 to C7) is not done yet, so their lines start short (spec Assumptions). The app server has 2 GiB of memory and keeps only the active snapshot locally, so reading 52 full snapshots per request is not possible.

**Decision**: Build a derived **price change log** per provider. It is built incrementally on local disk under `PRICING_HISTORY_DIR/<provider>/` as Parquet files, and can always be rebuilt from the snapshots. `PRICING_HISTORY_DIR` is a new setting that defaults to a persistent per-user folder (`~/.cloud-pricing/history`), not the temp folder, and is not counted in `PRICING_CACHE_MAX_BYTES`, so a restart or reboot never repeats the backfill:

1. **Comparable price list**: one per snapshot, from `comparable_prices(snapshot)`. Each row is `(location, item_key, service_key, unit, on-demand price on the first non-zero tier)`. Only the newest list per provider is kept, to diff against the next one.
2. **Week pair**: snapshots are grouped by ISO week, and the latest snapshot (latest revision) in each week represents it; the pipeline can publish several snapshots in a week (the local AWS store has 24 dates from 2026-08-30 to 2026-10-05). For each pair of consecutive weeks, the builder writes two files:
   - `changes`: one row per item whose price changed: location, item key, service key, description, unit, old price, new price.
   - `counts`: per (location, service key), the number compared, unchanged, increased, decreased, added, removed, and excluded (missing or zero price).

   Each file records both snapshot dates and revisions, so provenance is preserved (Principle I).
3. **When it runs**: in the snapshot monitor, after a provider's active snapshot switches, and on first start as a **backfill**. The backfill walks the provider's manifests oldest to newest, one snapshot at a time. Each historical snapshot is processed once, ever (`state.json` records it). With an S3 source, only the tables `comparable_prices` needs are fetched (AWS: `price_fact` and `product_dim`, about 204 of 271 MB per snapshot), with the existing size and SHA-256 verification, reduced to its price list, and deleted. With a `file://` source they are read in place with no copy. Weekly updates fetch nothing extra, because the newly active snapshot is already cached. Memory stays within the DuckDB limits (R2). The Admin tab shows per provider how many weeks are built, any gaps, and the last error.
4. **When the history changes**: a re-published revision of an already-built week rebuilds that week's pair and the pair after it.

The metrics read only these small files:

- **SKUs Changed** for week *w*: increased and decreased, summed from `counts` over the selected locations and service keys, with compared and excluded for the hover and the % of compared (R11).
- **Movers** over a period: for each (location, item), the price before its first change in the window and after its last change. Items that changed and changed back are dropped. Items removed before the period ended are dropped.

**Rationale**: List prices change rarely, so the change log is tiny compared with the snapshots. It answers every metric exactly, and it keeps derived data out of Postgres (Principle II) as a rebuildable, traceable cache.

**Alternatives considered**:
- Querying historical Parquet on S3 per request: too slow and too much memory.
- Backfill by querying S3 in place (DuckDB httpfs, only the needed columns, about 55 MB per AWS snapshot): about a quarter of the transfer, but no whole-file SHA-256 check (only size and row counts), plus S3 credentials inside DuckDB and slower range requests. The verified table-limited download is a one-time ~10 GB for 52 AWS weeks (about $0.90 to a laptop, free to EC2 in the same region). Revisit if history grows or backfills repeat.
- Storing full weekly price lists: 52 × 3 providers of full lists on disk for no extra metric.
- Storing aggregates in Postgres: Principle II forbids derived pricing values there.

## R11. Chart metric: SKUs Changed (the "0% median" finding)

**Finding**: Measured on the local AWS us-west-2 snapshots from 2026-09-15 to 2026-10-05 (10 consecutive pairs, on-demand, first tier): about 122,000 SKUs compared per pair, **1 price change in total**, and 18 to 2,826 SKUs added or removed per pair. Any median of per-SKU % changes is 0%, and a chained median index would be a flat line. A median *price* per category mixes unrelated units ($/GB-month, $/request, $/hour) and moves with added and removed SKUs, so it measures catalog churn, not price changes.

**Decision** (spec FR-012, FR-015, clarification 2026-11-03):

- **One chart metric, SKUs Changed**: per week and provider, the number of compared SKUs whose price went up and the number that went down. A SKU's change is (current − previous) ÷ previous. Only SKUs with a valid, non-zero price in both weeks are compared; new SKUs and removed SKUs are not changes (FR-013).
- **Hover**: up and down as counts and as % of compared, plus compared and excluded.
- **Removed**: Price Trend and Cumulative Change. The metric picker is removed from the page and the API. The change log keeps every changed price (`changes`), so either metric can be added later without rebuilding history.
- **Category filter**: it filters `counts` (and `changes` for movers) by the service keys that map to the category (R9).

**Alternatives considered**: median of changed SKUs only (shows one SKU's change most weeks; Biggest Movers shows that better, with names); mean over all compared SKUs (values near 0.0003%, dominated by single outliers); median price per category (above).

## R12. User preferences (FR-020 to FR-025)

**Decision**:

- **Storage**: a `user_preferences` table with one row per user: `user_id` (primary key, foreign key to `users`), `data` (JSONB), `schema_version`, `updated_at`. The JSON is validated by a typed Pydantic model with optional sections (`workspace`, `trends.charts`, `trends.movers`, `migrated_from_browser`), mirrored in TypeScript (Principle IV). Unknown sections are rejected, so new preferences are added by extending the model, not by writing free-form JSON.
- **API**: `GET /me/preferences` and `PATCH /me/preferences`. A PATCH replaces whole top-level sections, so the two Trends Resets don't overwrite each other, and the last write wins per section. Guests get their own row, which is deleted with the guest identity.
- **Moving browser settings**: on first load, if `migrated_from_browser` is false, the frontend sends the existing browser values for column widths and collapsed columns, then sets the flag. Settings tied to one architecture stay in the browser (clarification).
- **Failed saves**: they are queued in memory and retried with backoff, and never block the user (FR-025).

## R13. Arrow styles and branching connectors (FR-026 to FR-030)

**Decision**:

- `data_connectors` gains two columns:
  - `arrow_style`: one of `none`, `one_way`, `two_way`, `one_to_many`, `many_to_one`; the default is `none`.
  - `arrow_reversed`: a boolean, default false. Reversing is **visual only**. It doesn't swap `from`/`to`, so a data transfer selection keeps its pricing region and price (FR-029).
- **Branching**: a new table `connector_branches` (`connector_id`, `collection_id`, created order) holds the extra boxes. For `one_to_many`, they are extra "to" boxes; for `many_to_one`, extra "from" boxes. A data transfer selection on a branching connector is priced once, from the primary `from_collection` region, exactly as today (FR-027a).
- **Box deletion**: deleting a branch box removes the branch. With two boxes left, the connector becomes ordinary (`one_way`). With one left, the connector is removed (spec edge cases).
- **Drawing**: the diagram (`@xyflow/react`) draws a branching connector as a trunk from the "one" side to a junction point, then one edge per branch. Markers come from React Flow's built-in arrow markers.
- **Phasing**: branching is the last phase of the tasks, so it can move to a later release on its own (spec Assumptions) while arrow styles and reversing still ship.

## R14. Charts on the Trends page

**Decision**: Add **Recharts** (MIT, React, SVG). It provides line and bar charts, tooltips and responsive containers, and the chart count is small. Chart colors and styles follow the project's tokens. The `dataviz` guidance is applied when the chart is built.

**Alternatives considered**: Hand-written SVG means more code for tooltips and axes. Chart.js is canvas-based and fits React and the tests less well.

## R15. Export and import

**Decision**: Keep `format_version: 1` and add optional fields: the connector's `arrow_style`, `arrow_reversed`, `branch_refs`, and the selection's `provider_options`. Files from older versions import with defaults. An older app ignores the new fields (`extra="ignore"`), so it imports the architecture without arrows. GCP and Azure architectures export and import through the same file, and import validation calls the provider adapter's `exists`.

## R16. Release dependency

**Finding**: Azure and GCP pricing is collected and validated, but the pipeline's production rollout (004 quickstart Part C, C2 onward) is still open.

**Decision**: The app reads Azure and GCP data from any 1.1 data source and enables a provider only when it has a usable snapshot (FR-001). Development and tests use local pipeline output and fixtures. The app release can ship before or after the pipeline rollout. Until the rollout, production shows GCP and Azure as disabled, with the reason "no snapshot available".
