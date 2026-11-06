# Data Model: Provider Icons and Price Change Fixes (020)

No database changes. Nothing new is stored in Postgres, and there is no migration. The changes are:

- an additive API field (§1)
- an additive request shape (§2)
- the per-browser Price Change records (§3, §4)
- generated, checked-in icon maps (§5)

## 1. SKU selection (API response, additive)

`SKUSelectionOut` gains one field, resolved from the pricing catalog at response time like
`product_family`, and never stored:

| Field | Type | Notes |
|---|---|---|
| `service_name` | string or null | The provider's display name of the selection's service, e.g. "Compute Engine", "Virtual Machines". Null when the SKU isn't found in the active snapshot. |

## 2. Snapshot selection (`POST /catalog/calculate-snapshot` request)

`CalculateSnapshotRequest`:

| Field | Type | Notes |
|---|---|---|
| `duration` | `monthly` or `yearly` | Unchanged. |
| `provider` | `aws`, `gcp` or `azure`, optional | **New.** The architecture's provider. Missing means `aws`. |
| `selections` | list of `SnapshotSelection` | Unchanged; an empty list is still a 400 `empty_snapshot`. |

`SnapshotSelection`:

| Field | Type | Notes |
|---|---|---|
| `service_code`, `sku`, `pricing_term`, `purchase_option`, `usage_quantity` | as today | Unchanged. |
| `region` | string or null, optional | **New.** The region the selection was priced in: its box's region, or a connector's "from" box's region. Missing or null means `AWS_PRICING_REGION`, which is today's behaviour. |
| `provider_options` | `ProviderOptions` or null, optional | **New.** The same tagged shape selections use (`gcp_machine` or `azure_vm`). Missing or null means none. |

**Validation**

- `provider_options` is validated exactly as on a selection:
  - its `kind` must match `provider`
  - `gcp_machine` needs `vcpus > 0`, `memory_gib > 0` and a `ram_sku`
- A mismatch is a 422, as on selection create and update.

**Pricing**

- The throwaway architecture takes `provider`, and its selections are grouped into one throwaway
  collection per distinct region.
- Pricing then runs through the same `calculate_architecture_price` path as every other
  calculation (Principle I).

## 3. Price Change baseline (browser, per architecture)

Kept in `localStorage` by `priorCalculation.ts`, under the same key as today.

**Version 2** (written by this feature after every calculation):

| Field | Type | Notes |
|---|---|---|
| `version` | `2` | New. |
| `total` | decimal string | As today. |
| `duration` | `monthly` or `yearly` | As today. |
| `selections` | list | Each entry has `service_code`, `sku`, `pricing_term`, `purchase_option` and `usage_quantity` (string), as today, plus `region` (string or null) and `provider_options` (object or null). |

**Version 1 (legacy).** No `version` field, and selections have only the original five fields. It
is still read, and treated as described below.

**Comparison key**

| Baseline | Key |
|---|---|
| Version 2 | the five fields, plus `region`, plus `provider_options` in canonical form (JSON with sorted keys, values as the API returns them; null when absent) |
| Legacy | the five fields only, so the upgrade by itself never counts as a change |

**Decision rule** (extends `decideBaselineUpdate`, R3)

| Baseline | Contents changed? | Duration changed? | Outcome |
|---|---|---|---|
| none | – | – | `establish` (as today) |
| any | no | no | `unchanged` (as today) |
| any | yes | no | `direct`: new total − previous total (as today) |
| v2 | any | yes | `duration_adjusted` or `duration_only`: previous selections re-priced at the new Duration, with provider, regions and options (as today, now with full settings) |
| legacy | any | yes | AWS architecture: as today. GCP or Azure architecture: **`unavailable`**, a new outcome. No value is shown, with the note "Not available: previous calculation from prior version is unreliable". |

Every outcome except `unchanged` stores a version 2 baseline. `unavailable` does too, so the next
calculation is exact.

## 4. Stored pricing result's priced contents (browser, per architecture)

This is the "updated since last pricing" notice's record (`architecturePricingResults.ts`).

- Each entry gains `provider_options` (object or null). A stored entry without the field is
  legacy, and is compared without options.
- `region` is already there.

## 5. Service icon maps (generated, checked in)

There is one generated TypeScript module per provider. They are written by
`backend/scripts/generate_provider_service_icon_map.py` and never edited by hand.

| Export | Shape | Notes |
|---|---|---|
| `<P>_SERVICE_ICON_BY_ID` | `Record<service_id, iconStem>` | One icon per service. |
| `<P>_SERVICE_ICON_OVERRIDES` | `Record<service_id, Array<{ match: string; icon: iconStem }>>` | Ordered, first match wins. GCP `match` is a taxonomy prefix (e.g. `GCP > Compute > GCE > Persistent Disk`). Azure `match` is a case-insensitive product-name pattern (e.g. `Managed Disks`). FR-008a. |

`<P>` is `GCP` or `AZURE`. Icon stems name files in `frontend/src/assets/<p>-icons/`.

**Resolution order** for one selection on a GCP or Azure architecture:

1. the first matching override for its service
2. its service's icon
3. the **fallback tile**: the provider logo plus a name

The name comes from, in order: `service_name`, then `attributes`/summary, then `service_code`.

AWS keeps `resolveAwsServiceIcon` and its generated module unchanged.
