# Research: GCP and Azure Standard Architectures

**Feature**: 022-gcp-azure-standard-architectures | **Date**: 2026-11-11

Findings are from the code on `main` (8541c1f), the local pricing data in `../_DATA-PIPELINE`
(GCP and Azure snapshots of 2026-11-02, AWS of 2026-10-05), and the data pipeline's region
configuration (`cloud-pricing-data-retrieval/src/pipeline/providers.py`, `infra/envs/prod.tfvars`).

## R1. Regions the pricing data actually has

**Finding**:
- Production collects GCP `us-east1`, `us-east4`, `us-west1`, `us-west2`, `europe-west1`,
  `europe-west2` and `asia-northeast1`.
- Production collects Azure `eastus`, `eastus2`, `westus`, `westus2`, `westeurope`, `uksouth`
  and `japaneast`.
- Azure `northeurope` is not collected.
- The local GCP and Azure snapshots hold US regions only. They were run with a narrower region
  list.

**Decision**:
- Use GCP `europe-west1` and Azure `westeurope` for the Serverless design. The spec is updated
  to match.
- Generation needs a local GCP and Azure snapshot that includes `europe-west1` and
  `westeurope`. Before generating, refresh the local data with the pipeline's default
  locations.

**Rationale**: A region the pipeline doesn't collect has no prices. The architecture would be
created but could never price, which breaks SC-002.

**Alternatives considered**:
- Add `northeurope` to the pipeline (the cloud-pricing-data-retrieval repo). Rejected: it
  changes another repo and adds collection cost, for a one-region difference (Ireland versus
  the Netherlands).
- Generate against the production S3 data. Rejected: the resolver reads only a local store
  (`LocalStore`), as in 014.

| Design | AWS | GCP | Azure |
|---|---|---|---|
| Web App, primary | us-east-1 | us-east1 | eastus |
| Web App, standby | us-west-2 | us-west1 | westus2 |
| Data Lake & ETL | us-east-1 | us-east1 | eastus |
| Serverless | eu-west-1 | europe-west1 | westeurope |
| EKS platform | us-west-2 | us-west1 | westus2 |

## R2. Services present in the pricing data

**Finding**: every service in the equivalents table has SKUs or meters in the data.
- **GCP:** Cloud DNS, Compute Engine, Cloud SQL, Cloud Storage, Networking (load balancing and
  egress), Cloud Pub/Sub, Cloud Dataflow, BigQuery, Identity Platform, API Gateway, Cloud Run
  Functions, Cloud Firestore, Kubernetes Engine, Artifact Registry, Cloud Memorystore for Redis.
- **Azure:** Azure DNS, Virtual Machines, Azure Database for PostgreSQL and for MySQL, Storage,
  Load Balancer, Bandwidth, Event Hubs, Azure Data Factory v2, Azure Synapse Analytics,
  "Azure Active Directory for External Identities" (Entra External ID), API Management,
  Functions, Azure Cosmos DB, Service Bus, Event Grid, Azure Kubernetes Service, Container
  Registry, Redis Cache.

Some of these are global-only: Cloud DNS, Pub/Sub, Identity Platform, Artifact Registry, Azure
DNS and Load Balancer.

**Decision**: a global-only service is placed in the design's first region's collection, the
same rule as the AWS "global" components (014 FR-006). It is priced from the `global`
location, which both adapters already read alongside the region (019 research R5).

**Note**: whether a figure finds a priced SKU or meter is settled per rule when the generator
runs. Anything that doesn't is left out and reported (FR-005). Nothing is decided here from
memory.

## R3. Generator: extend the AWS resolver per provider

**Decision**:
- Keep `scripts/resolve_standard_architectures.py` as the single command and add
  `--provider aws|gcp|azure`, defaulting to `aws`.
- Keep `match_rules.py` as AWS. Add `match_rules_gcp.py` and `match_rules_azure.py`.
- `resolver.py` gets one SKU finder per provider, each reading that provider's own tables:
  - AWS: the existing `product_dim` / `price_fact` query, unchanged.
  - GCP: `sku` plus `sku_price` with consumption model `Default`.
  - Azure: `price_item` with `type = 'Consumption'`.
- The report renderer, the export builder and the unit check are shared.
- Each provider's snapshot is selected with `select_snapshot(store, provider, …)`, instead of
  the module-level AWS `PROVIDER`.

**Rationale**:
- This is Principle III: provider-specific retrieval behind a shared shape. AWS output stays
  byte-identical (FR-009, SC-006).
- The choice stays deterministic, as in 014: candidates are tried in order, and the lowest
  SKU or meter id wins (SC-005).

**Alternatives considered**:
- Search the app's catalog through the provider adapters. Rejected: the catalog is built for
  people searching, not for exact attribute matching, and its ordering isn't a stable
  contract.
- One combined rules file with a provider field. Rejected: about 150 rules in one file is hard
  to review, and each provider's filter vocabulary differs.

## R4. GCP and Azure rule shape

**Decision**: a rule carries the following.
- `aws_component_id` and `figure`: the AWS component and usage figure it stands in for (FR-011).
- `region`, from R1.
- Provider filters:
  - GCP: `service` (display name), `display_name` (exact or a regular expression),
    `taxonomy_contains`, `expected_unit`.
  - Azure: `service_name`, `product_name`, `sku_name`, `meter_name`, `arm_sku_name`,
    `expected_unit`.
- `quantity`, using the same daily-rate formulas as AWS. They are moved into a shared module,
  `standard_architectures/quantities.py`, so all three providers convert usage the same way.
- `provider_options` (machines only, R6).
- `omit_reason`, `note`, and `size_note`. The size note gives the original and the chosen
  size (FR-003).

**Rationale**: every figure's choice is explicit and reviewable in code, the same "auditable
table, never a heuristic" approach as 014.

## R5. Usage conversions to each provider's billing units

**Decision**: each provider figure is derived from the AWS reference's underlying workload
figures, never from AWS billing units. The reference is
`docs/brief/common_aws_architectures.md`.

| AWS figure | GCP | Azure |
|---|---|---|
| Route 53 queries | Cloud DNS queries (same count) | Azure DNS queries (same count) |
| ALB/NLB hours and LCU-hours | forwarding-rule hours, plus data processed by the load balancer where the reference gives a volume, else left out with reason | Load Balancer rule hours, plus data processed (same rule) |
| EC2 hours (4 × t4g.xlarge, 6 × m6i.large) | Compute Engine machine-hours, sized by R6 | VM hours, sized by R6 |
| Aurora / RDS instance hours and storage | Cloud SQL vCPU-hours and GiB-hours (R6), plus storage GiB-months | Flexible Server vCore hours (R6), plus storage GB-months |
| S3 storage and requests | Cloud Storage Standard GiB-months; Class A (PUT) and Class B (GET) operations | Hot LRS block blob GB-months; write and read operations |
| S3 Glacier Instant Retrieval | Cloud Storage Archive or Coldline, whichever is the like-for-like "instant retrieval, rarely read" class | Cool or Cold tier, by the same rule |
| Cross-region replication transfer (250 GB) | inter-region egress, us-east1 to us-west1 | inter-region data transfer, eastus to westus2 |
| Kinesis 500,000 MB per month ingested | Pub/Sub throughput (TiB) | Event Hubs throughput unit hours, plus ingress events |
| Glue 10 DPU × 2 h per day (1 DPU = 4 vCPU, 16 GB) | Dataflow vCPU-hours (40 × 2 h) and memory GB-hours (160 × 2 h) | Data Factory data-flow vCore-hours (40 × 2 h) |
| Glue Data Catalog | left out: no equivalent in the confirmed table | left out: same reason |
| Athena 60 TB scanned | BigQuery on-demand TiB scanned | Synapse serverless SQL TB processed |
| Redshift Serverless 240 RPU-hours | left out: RPU-hours have no like-for-like unit (BigQuery storage has no AWS figure to size it from, and slot-hours would be a forced conversion) | left out: same reason (Synapse dedicated SQL pool DWU-hours aren't comparable to RPU-hours) |
| Cognito 10,000 MAU | Identity Platform MAU | External ID MAU |
| API Gateway 20M requests | API Gateway calls | API Management Consumption calls |
| Lambda 15M executions × 250 ms × 1 GB | Cloud Run functions invocations, vCPU-seconds and GiB-seconds | Functions executions and GB-seconds |
| DynamoDB 50 GB, 5M reads, 2M writes | Firestore stored GiB, document reads and writes | Cosmos DB serverless storage and request units |
| SQS 10M and SNS 2M requests | Pub/Sub (one throughput figure for both) | Service Bus operations; Event Grid operations |
| EKS control plane hours | GKE cluster-management hours | AKS: the Free tier has no charge, so left out with reason (or the Standard tier, if the data prices it as a cluster-hour) |
| Fargate 10 pods × 1 vCPU × 2 GB | GKE Autopilot pod vCPU-hours and memory GiB-hours (a direct 1:1 of vCPU and GiB hours, inside GKE) | left out: AKS has no per-pod price, and Container Instances isn't in the confirmed table |
| ECR 100 GB | Artifact Registry GiB-months | Container Registry: the tier whose included storage covers 100 GB |
| App Mesh | left out: no charge in the AWS original | left out: same reason |
| ElastiCache 2 × cache.m6g.large | Memorystore for Redis GB-hours at the capacity sized by R6 | Azure Cache for Redis node hours at the cache size from R6 |
| CloudFront (all figures) | left out, to match the AWS version (CDN isn't in the confirmed table) | left out, same reason |

**Guiding rule (owner, 2026-11-11)**: no complex logic to force a mapping. A figure is matched
only when the counterpart bills the same kind of unit (hours, GB, requests, vCPU-hours) and
needs at most a simple scale (for example 1 DPU = 4 vCPU). Otherwise it is left out with the
reason.

Components the AWS version leaves out (CloudFront, Route 53 hosted zones and health checks,
App Mesh, gp3 baseline IOPS) are left out of the equivalents too, so the three totals cover
the same scope. The report gives the reason.

## R6. Sizing rule (clarification 2): the smallest size at least as large

**Decision**:

| AWS size | vCPU / GiB | GCP | Azure |
|---|---|---|---|
| t4g.xlarge (web app) | 4 / 16 | e2-standard-4 (4 / 16) | Standard_D4s_v5 (4 / 16), Linux |
| m6i.large (EKS nodes) | 2 / 8 | e2-standard-2 (2 / 8) | Standard_D2s_v5 (2 / 8), Linux |
| db.r6g.xlarge (Aurora) | 4 / 32 | Cloud SQL for PostgreSQL Enterprise, 4 vCPU / 32 GiB (custom) | PostgreSQL Flexible Server, Memory Optimized E4ds_v5 (4 / 32) |
| db.m6g.xlarge Multi-AZ (MySQL) | 4 / 16 | Cloud SQL for MySQL Enterprise, 4 vCPU / 16 GiB, high availability (regional) | MySQL Flexible Server, General Purpose D4ds_v4 (4 / 16), zone-redundant high availability |
| cache.m6g.large (Redis) | 2 / 6.38 | Memorystore Standard tier, 7 GB (the smallest whole-GB capacity of at least 6.38 GiB) | Azure Cache for Redis Standard C4 (13 GB; C3 is 6 GB, below 6.38) |

- The x86 general-purpose families (E2, Dsv5) are used even where AWS uses Graviton (ARM). This
  is the most common, widely available counterpart. The note records it.
- GCP machines use `gcp_machine` options (`vcpus`, `memory_gib`, `ram_sku`), with the core SKU
  as the selection's SKU. The same core × vCPU + RAM × GiB pricing already works for any core
  and RAM SKU pair billed in `h` and `GiBy.h` (`providers/gcp.py` `_machine_quote`), so Cloud
  SQL instances use it too, with the Cloud SQL vCPU and RAM SKUs. This needs no engine change.
- Azure VMs use `azure_vm` options `{os: "linux"}`.
- Every chosen size is confirmed against the data by the generator. If a size has no price,
  the next size up that meets the rule is chosen, and the note says so.

## R7. Seeding: a new migration and one seed file per provider

**Decision**:
- New Alembic revision `0009_gcp_azure_standard_architectures`, after `6c3e9a1b5f08` (0008).
- It reads `src/db/seed/standard_architectures_gcp.json` and `standard_architectures_azure.json`.
- It inserts the architectures with plain SQL, like 0005, but adds two things:
  - `provider_options` is inserted (JSON) on SKU selections;
  - the "already exists" check is on owner, name and provider among non-deleted
    architectures.
- No default Admin: return without inserting. Downgrade deletes only Admin-owned GCP and Azure
  architectures with the seeded names.
- 0005 is left unchanged.

**Rationale**:
- An Alembic revision runs exactly once per database. That gives "created once, never
  recreated or renamed back" (FR-008) without a marker table.
- The migration also reaches every environment through `ops db-init`, which runs
  `alembic upgrade head` on every bring-up (FR-007). That includes restores from older backups,
  which the v0.1.1 fix proved.
- The skip by name and provider handles a partly applied earlier state.

**Alternatives considered**:
- Extend 0005. Rejected: it has already run in every database, so a change would never apply.
- A startup seeder in the app. Rejected: it can't tell "deleted by the Admin" apart from
  "never created" without a new marker table.

**Note**: 0005's downgrade deletes Admin architectures by name only, so it would also remove the
GCP and Azure ones. It only matters when downgrading below 0005, which never happens in
operation. Left alone, as the input asked.

## R8. Collections and names

**Decision**:
- Architecture names are identical to the AWS ones (spec assumption).
- One collection per design region, in the AWS order, type `vpc`. They are named
  "VPC (us-east1)" on GCP and "VNet (eastus)" on Azure, each provider's own term.
- No connectors and no nesting.
- Every selection is `on_demand`, with `not_applicable` purchase option, as for AWS.

## R9. Test data and tests

**Decision**:
- `scripts/build_provider_fixtures.py` adds every SKU or meter used by the two new seed files,
  read from the seed files, like `build_test_pricing_fixture.py`'s
  `_standard_architecture_skus()`.
- It also adds the `europe-west1`, `westeurope` and `us-west1` / `westus2` locations to the GCP
  and Azure fixtures.
- Tests, written first (Principle V):
  - **Unit:** the GCP and Azure finders against a tiny inline Parquet set. Deterministic
    choice, unrecognized unit failing the run, omissions.
  - **Unit:** the shared quantity formulas, unchanged results for AWS.
  - **Unit:** report rendering with the AWS-component column and size notes.
  - **Integration:** each new seed file passes the Admin import validation against the
    fixture (every SKU exists in its region).
  - **Integration:** each of the eight prices with no unpriceable items and a non-zero total
    (SC-002).
  - **Integration:** migration 0009 inserts 8 public Admin architectures once. It skips a
    same-name, same-provider one, and it does not skip a same-name AWS one. With no default
    Admin it does nothing. Running it again adds none.
  - **Integration:** restoring a backup taken at 0008 (or at 0005), then upgrading, adds
    exactly eight (SC-003). This extends `test_db_init_restore.py`.
  - **Regression:** the AWS seed is unchanged (SC-006). Re-running generation is
    byte-identical (SC-005), checked by a test that re-renders from the fixture.
- An optional Playwright check opens one GCP and one Azure standard architecture and
  calculates it.

## R10. Mapping data for agent-04

**Decision**: no separate mapping file. The report's matched rows name the AWS component each
one stands in for (FR-011), and the seed files hold the chosen SKUs. agent-04 will decide its
own mapping format and seed it from these.

**Rationale**: Principle VI. A machine-readable mapping file would be built for a feature that
isn't being implemented yet.

**Alternative considered**: write `standard_architectures_matches.json` now. Rejected for that
reason. It can be added in agent-04, where its format is known.
