# Data Model: GCP and Azure Standard Architectures

**Feature**: 022-gcp-azure-standard-architectures

This feature has no schema change. It adds rows to the existing tables, and two generated
files plus one reference input to the repo.

## 1. Database rows (existing tables)

Migration `0009` inserts the following under the user with `is_default_admin = true`.

| Table | Rows | Notes |
|---|---|---|
| `architectures` | 8: 4 with `provider = 'gcp'`, 4 with `provider = 'azure'` | `name` identical to the AWS original; `is_public = true`; `created_at` and `updated_at` from `clock_timestamp()` |
| `collections` | 1 per design region: Web App 2, Data Lake 1, Serverless 1, EKS 1 | `type = 'vpc'`; `name` "VPC (&lt;region&gt;)" on GCP, "VNet (&lt;region&gt;)" on Azure; `region` from research R1; no parent |
| `sku_selections` | 1 per matched figure | `service_code`, `sku`, `pricing_term = 'on_demand'`, `purchase_option = 'not_applicable'`, `usage_quantity` as Numeric(18,4), and `provider_options` (JSON or null) |

**Identity rule (FR-008)**: an architecture is skipped when the Admin already owns a
non-deleted architecture with the same `name` and the same `provider`. The same name on
another provider doesn't count.

**Lifecycle**: inserted once, by an Alembic revision that runs once per database. Afterwards
the rows are ordinary Admin architectures: the Admin can rename or delete them, and no later
release recreates or changes them.

**`provider_options`** (existing 019 shapes, `src/models/schemas.py`):
- A GCP machine or Cloud SQL instance:
  `{"kind": "gcp_machine", "version": 1, "vcpus": <int>, "memory_gib": "<decimal>", "ram_sku": "<sku_id>"}`.
  The selection's `sku` is the core (vCPU) SKU.
- An Azure VM: `{"kind": "azure_vm", "version": 1, "os": "linux"}`.
- Everything else: null.

## 2. Seed files (generated, checked in, never hand-edited)

`backend/src/db/seed/standard_architectures_gcp.json` and `standard_architectures_azure.json`
are in the existing architecture export format (`ArchitectureExportFile`, format version 1):
- `exported_at` is the snapshot date at 00:00 UTC, which keeps the file deterministic;
- `source_username` is `"Admin"`;
- `architectures[]` holds four `ArchitectureDefinition`s, each with `provider` `gcp` or `azure`;
- each `CollectionDefinition` has a `ref`, a `region` and `sku_selections[]`, and each
  `SKUSelectionDefinition` may carry `provider_options`.

The existing `standard_architectures.json` (AWS) is unchanged.

**Validation**: each file passes `validate_definition`, the Admin import's validator, against
the pricing data. That proves every `(service_code, sku)` exists in its collection's region,
global included.

## 3. Reports (generated, checked in, never hand-edited)

`backend/src/db/seed/standard_architectures_gcp_report.md` and
`standard_architectures_azure_report.md` follow the AWS report's layout (contract:
`contracts/generator.md`), with two more columns:
- **AWS component**: the reference component id the row stands in for (FR-011);
- **Size**: "original → chosen" for sized resources (FR-003), for example
  "t4g.xlarge 4/16 → e2-standard-4 4/16".

A **Left out** table per architecture lists the AWS component, the figure and the reason.

## 4. Match rule (generator input, code)

These live in `backend/scripts/standard_architectures/match_rules_gcp.py` and
`match_rules_azure.py`.

| Field | Meaning |
|---|---|
| `architecture_id` | The reference design id, for example `arch_web_multi_region_active_standby` |
| `aws_component_id`, `figure` | The AWS component and usage figure this rule stands in for |
| `region` | The provider region (research R1); global-only services use the design's first region |
| Provider filters | GCP: `service`, `display_name` or `display_name_regex`, `taxonomy_contains`, `expected_unit`. Azure: `service_name`, `product_name`, `sku_name`, `meter_name`, `arm_sku_name`, `expected_unit` |
| `quantity` | From the shared formulas in `quantities.py`, using the engine's daily-rate convention |
| `provider_options` | For GCP machines and Cloud SQL, or Azure VMs (research R6) |
| `size_note` | Original and chosen size, when sized |
| `omit_reason` | Set when the figure is deliberately left out; no lookup is done |
| `note` | Any other remark for the report |

**Rules**:
- Every figure of every AWS reference component has exactly one rule per provider (SC-004).
- Within a rule, the candidates are tried in order, and the lowest SKU or meter id wins
  (SC-005).
- A chosen SKU billed in a unit the engine can't classify fails the run.

## 5. Reference input

`docs/brief/common_aws_architectures.md` (JSON) stays the single source for the designs: their
ids, names, components and usage figures. The GCP and Azure regions are in the rule modules,
with the AWS-to-provider region mapping table at the top of each, so the reference needs no
change.
