# GCP pricing fixture (019, T005)

Snapshot `2026-11-02`, revision 1, manifest 1.1, built by `scripts/build_provider_fixtures.py`
from the local pipeline root. Rows are copied verbatim and in source order; nothing is edited.
Locations: `us-east1`, `global`. Tables: `service` (global partition only; `us-east1` lists no
files), `sku`, `sku_price`, `sku_price_tier`.

Every price below is the `sku_price_tier.list_price` for `start_amount = 0` unless tiers are
shown. All `unit_quantity` values are 1. Prices are USD as published.

## `us-east1`

| What | `sku_id` | `display_name` | Geo | Unit | Default | CUD 1 year | CUD 3 year |
|---|---|---|---|---|---|---|---|
| N2 core | `BB77-5FDA-69D9` | N2 Instance Core running in Americas | multi-regional (us-central1, us-east1, us-west1) | h | **0.031611** | 0.02275992 | 0.01706994 |
| N2 RAM | `5B01-D157-A097` | N2 Instance Ram running in Americas | multi-regional | GiBy.h | **0.004237** | 0.00305064 | 0.00228798 |
| N2 custom, custom extended, sole tenancy, sole-tenancy premiums | 9 SKUs (`3E94-…`, `5304-…`, `E8A6-…`, `04AB-…`, `A8F6-…`, `B27B-…`, `7E17-…`, `1735-…`, `3695-…`) | same taxonomy (`VMs On Demand`, `N2`) | multi-regional | h / GiBy.h | (excluded by the display-name filter) | | |
| Balanced PD | `6AE1-525F-8B80` | Balanced PD Capacity | multi-regional | GiBy.mo | **0.1** | | |
| Regional balanced PD | `0FE3-CAB9-E7E3` | Regional Balanced PD Capacity | multi-regional | GiBy.mo | 0.2 | | |
| Standard storage, US regional | `E5F0-6A5D-7BAD` | Standard Storage US Regional | multi-regional | GiBy.mo | tiers 0 @ 0, 5 @ **0.02** | | |
| Standard storage, other | `0D5D-…` US Multi-region 0.026; `420D-…` Iowa/South Carolina Dual-region 0.044; `1CAF-…` South Carolina Dual-region (regional) 0.022 | | | GiBy.mo | | | |
| Internet egress, GCE Premium | `F274-1692-F213` | Network Internet Data Transfer Out from Americas to Americas | multi-regional | GiBy | tiers 0 @ 0, 1 @ **0.12**, 1024 @ 0.11, 10240 @ 0.08 | | |
| Internet egress, Cloud SQL | `238B-D94B-7243` | same display name, taxonomy `Cloud SQL` | multi-regional | GiBy | 0.19 (not the GCE egress kind) | | |
| Cloud SQL Postgres vCPU | `965E-7C36-08E6` | Cloud SQL for PostgreSQL: Zonal - vCPU in Americas | multi-regional | h | 0.0413 | 0.030975 | 0.019824 |
| Cloud SQL Postgres RAM | `93DA-3F55-CB04` | Cloud SQL for PostgreSQL: Zonal - RAM in Americas | multi-regional | GiBy.h | 0.007 | 0.00525 | 0.00336 |

The Cloud SQL commitments are described as `Cloud SQL CUD - 1 Year` / `- 3 Year`; the Compute
ones as `Compute Flexible CUD - 1 Year` / `- 3 Year`.

## `global`

| What | `sku_id` | `display_name` | Geo | Unit | Price |
|---|---|---|---|---|---|
| Windows Server 2022 Datacenter licence (global-only) | `92D2-8A8F-DF54` | Licensing Fee for Windows Server 2022 Datacenter Edition on VM | `TYPE_GLOBAL` | h | **0.046** |

## Expected results

- `n2-standard-4` (4 vCPUs, 16 GiB), on demand, per hour: 4 × 0.031611 + 16 × 0.004237 = 0.126444 + 0.067792 = **0.194236**.
  - CUD 1 year: 4 × 0.02275992 + 16 × 0.00305064 = **0.13984992**.
  - CUD 3 year: 4 × 0.01706994 + 16 × 0.00228798 = **0.10488744**.
- 500 GiB per month of GCE Premium egress: 1 × $0 + 499 × $0.12 = **$59.88**.
- No row has a null `list_price` (the real data has none). Tests of the null case write their own rows.
