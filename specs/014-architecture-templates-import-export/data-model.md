# Data Model: Standard Architectures and Admin Architecture Import/Export

**Feature**: 014-architecture-templates-import-export | **Date**: 2026-09-25

**No Postgres schema changes.** This feature adds data (the seeded standard architectures) and in-memory transfer shapes. It adds no tables or columns (research §1, §11).

## Existing entities (unchanged schema)

| Entity | How this feature uses it |
|---|---|
| `User` | The default Admin (`is_default_admin = true`) owns the four standard architectures. Admin import targets any named user (`username IS NOT NULL`). |
| `Architecture` | Standard architectures are ordinary rows with `user_id = <Admin>`, `provider = 'aws'` and `is_public = true`. Imported architectures get `is_public = false` (FR-023). |
| `Collection` | Standard architectures have only `type = 'vpc'` collections, one per listed region, named `VPC (<region>)` (e.g. `VPC (us-east-1)`), with no parent. Import recreates any collection type and nesting. |
| `DataConnector` | None in standard architectures (FR-007). Import recreates connectors between collections of the same architecture. |
| `SKUSelection` | Standard architectures: one row per matched usage figure, `pricing_term = 'on_demand'`, `purchase_option = 'not_applicable'`, `usage_quantity` from research §5. Import copies all five pricing fields as-is. |

## Derived API field

- **`AdminUserOut.architecture_count: int`** — the number of the user's architectures with `deleted_at IS NULL`. Computed per request; drives the Export button's disabled state (FR-012).

## Architecture Export File (transfer document, not persisted)

This is the full JSON contract, defined in [contracts/export-format.md](contracts/export-format.md). In summary:

```text
ArchitectureExportFile
├── format: "cloud-pricing-architectures"   (literal)
├── format_version: 1                       (supported set: {1})
├── exported_at: ISO-8601 UTC timestamp
├── source_username: str                    (informational only; ignored on import)
└── architectures: [ArchitectureDefinition]   (0..n; each validated individually)

ArchitectureDefinition
├── name: str (1..255, trimmed, non-empty)
├── provider: "aws" | "gcp" | "azure"
├── collections: [CollectionDefinition]
└── connectors: [ConnectorDefinition]

CollectionDefinition
├── ref: str                  (file-local key, unique within its architecture — never a DB id)
├── type: "vpc" | "application_component"
├── name: str (1..255)
├── region: str               (must be an available pricing region)
├── parent_ref: str | null    (only for application_component; must reference a vpc in this architecture)
└── sku_selections: [SKUSelectionDefinition]

ConnectorDefinition
├── from_ref: str             (collection ref in this architecture)
├── to_ref: str               (≠ from_ref)
└── sku_selection: SKUSelectionDefinition | null

SKUSelectionDefinition
├── service_code: str
├── sku: str
├── pricing_term: "on_demand" | "reserved_1yr" | "reserved_3yr"
├── purchase_option: "no_upfront" | "partial_upfront" | "all_upfront" | "not_applicable"
└── usage_quantity: decimal ≥ 0, ≤ 4 decimal places
```

**Excluded by design (FR-016)**: database ids, owner id, `is_public`, soft-deleted rows, timestamps other than `exported_at`, and any price value.

## Validation rules (import, per architecture — FR-021)

These checks run in order, and the first failure becomes the row's error message:

| # | Rule | Error message (examples) |
|---|---|---|
| 1 | Entry matches `ArchitectureDefinition` (types, required fields, enums) | `Invalid architecture definition: <field> <problem>` |
| 2 | `name` not already used by one of the target user's non-deleted architectures, or by an earlier successful entry in this file | `Architecture name already exists` |
| 3 | Collection `ref`s unique; every `parent_ref`, `from_ref` and `to_ref` resolves in this architecture; `from_ref ≠ to_ref` | `Invalid reference: connector points to unknown collection "c9"` |
| 4 | Only `application_component` has a `parent_ref`, and its target has `type = vpc` | `Invalid nesting: "Web tier" must be inside a VPC` |
| 4a | `provider` is `aws` (the only provider with pricing data today) | `Provider not supported: gcp` |
| 5 | Every collection `region` is in `list_available_regions()` | `Region not available in pricing data: ap-south-1` |
| 6 | Every `(service_code, sku)` exists in the latest snapshot for its owning collection's region. A connector's selection uses its `from` collection's region, matching the existing pricing rule. | `Service not found in pricing data: AmazonXYZ / ABC123 (us-east-1)` |

Whole-file rejection (FR-019) happens before these checks. It applies when the body isn't a JSON object, `format` is wrong, `format_version` isn't supported, or `architectures` is missing or not a list.

## Import Result (response item, not persisted)

```text
ImportResult
├── name: str | null     (the entry's name if readable, else null → UI shows "(unnamed #n)")
├── status: "success" | "failed"
└── error: str | null    (brief reason; null on success)
```

Results are returned in file order, one per `architectures[]` entry (FR-022).

## Standard architecture seed (checked-in data)

- **`backend/src/db/seed/standard_architectures.json`** — an `ArchitectureExportFile` holding the four standard architectures. It is generated by the resolver script (research §1–§5) and never hand-edited.
- **`backend/src/db/seed/standard_architectures_report.md`** — generated. For each figure it records the matched SKU and unit, or the reason it was left out: e.g. App Mesh has no records, gp3 IOPS is included in the baseline, Aurora Multi-AZ isn't expressible (FR-010, FR-009a). It also flags SKUs that have tiered price rows (research §7).
- **Migration `0005_standard_architectures`** — inserts the seed under the default Admin with `is_public = true`. It skips any architecture whose name the Admin already owns, as a defensive guard. Downgrade deletes the Admin's architectures with those four exact names.

## State transitions

Architecture lifecycle is unchanged. Two new ways a row can be created:
- **Seed (migration):** `∅ → Architecture(owner=Admin, is_public=true)`. It runs once per database.
- **Admin import:** `∅ → Architecture(owner=target user, is_public=false)`. It happens per successful entry.
