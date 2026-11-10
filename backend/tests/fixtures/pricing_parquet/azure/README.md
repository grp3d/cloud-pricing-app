# Azure pricing fixture (019, T004)

Snapshot `2026-11-02`, revision 1, manifest 1.1, built by `scripts/build_provider_fixtures.py`
from the local pipeline root. Rows are copied verbatim and in source order; nothing is edited.
Locations: `eastus`, `global`, `north-america` (a geography partition, never a selectable region).
Tables: `price_item`, `price_item_savings_plan`.

An item is `<sku_id>/<meter_id>` (research R4). Prices are USD as published.

## `eastus`

| What | Item (`sku_id/meter_id`) | `product_name` / `sku_name` | Price type | Unit | Price |
|---|---|---|---|---|---|
| D4s v5 Linux | `DZH318Z08M9W/004T/db8c0962-…` | Virtual Machines Dsv5 Series / `Standard_D4s_v5` | Consumption | 1 Hour | **0.192** |
| D4s v5 Linux, 1-year reservation | `DZH318Z08M9W/01X9/db8c0962-…` | same | Reservation `1 Year` | 1 Hour (whole-term fee) | **1038.0** |
| D4s v5 Linux, 3-year reservation | `DZH318Z08M9W/01X3/db8c0962-…` | same | Reservation `3 Years` | 1 Hour (whole-term fee) | **1993.0** |
| D4s v5 Linux, savings plan | key `92e4de9c…` (`price_item_savings_plan`) | same | `1 Year` / `3 Years` | 1 Hour | **0.1316736** / **0.0883584** |
| D4s v5 Linux Spot / Low Priority | `…/004R/…`, `…/004S/…` | `Standard_D4s_v5 Spot` / `Low Priority` | Consumption | 1 Hour | 0.040531 / 0.0384 (excluded by the VM filter) |
| D4s v5 Windows | `DZH318Z08M9T/00CS/57bde05c-…` | Virtual Machines Dsv5 Series Windows | Consumption | 1 Hour | **0.376** |
| D4s v5 Windows, DevTest, Spot, Low Priority | `…/00CS`, `…/00F5`, `…/00CX` | Windows | DevTestConsumption / Consumption | 1 Hour | 0.192, 0.079374, 0.15, … (excluded) |
| P10 LRS managed disk | `DZH318Z0BP04/0035/93a6a529-…` | Premium SSD Managed Disks / P10 LRS | Consumption | 1/Month | **19.71** |
| P10 LRS page blob (same meter name) | `DZH318Z0BP0W/00H7/05212985-…` | Premium Page Blob / P10 LRS | Consumption | 1/Month | 19.71 (not the block-storage kind) |
| Egress, Microsoft network | `DZH318Z0BNVX/001D/9995d93a-…` | Rtn Preference: MGN / Standard | Consumption | 1 GB | tiers from 0 @ **0**, 100 @ 0.087, 10335 @ 0.083, 51295 @ 0.07, 153695 @ 0.05, 512095 @ 0.05 |
| Egress, internet route | `DZH318Z0C8ZQ/000K/6bd64e8e-…` | Bandwidth - Routing Preference: Internet | Consumption | 1 GB | tiers from 0 @ 0, 100 @ 0.08, 10100 @ 0.065, 50100 @ 0.06, 150100 @ 0.04 |
| Hot LRS blob storage | `DZH318Z0BPH7/006M/272492b3-…` | General Block Blob v2 / Hot LRS | Consumption | 1 GB/Month | tiers from 0 @ 0.0208, 51200 @ 0.019968, 512000 @ 0.019136 |
| Duplicate-name meter (R8) | `DZH318Z0BPH7/006M/14854f12-…` | General Block Blob v2 / Hot LRS; meter names `Hot LRS Write Operations` and `LRS List and Create Container Operations` | Consumption | 10K | two rows, tier start 0, both **0.05**: collapses to one tier |
| PostgreSQL Flexible Server, 2 vCore | `DZH318Z0KDZJ/00D3/71f7052a-…` | …General Purpose Ddsv5 Series Compute / 2 vCore | Consumption | 1 Hour | **0.178** (savings plan `1 Year` 0.1424) |

## `global`

| What | Item | Price type | Unit | Price |
|---|---|---|---|---|
| SQL Server Standard licence, 1–4 vCPU VM (global-only) | `DZH318Z0BJTS/0003/6b44a2ed-…` | Consumption / DevTestConsumption | 1 Hour | **0.4** / 0.0 (savings plan `1 Year` and `3 Years` 0.4) |

The data has no Azure support plans, so the global-only item is a licence.

## `north-america`

| What | Item | Unit | Price |
|---|---|---|---|
| Bandwidth Alliance egress | `DZH318Z0DDZ3/0002/b9668c9e-…` | 1 GB | 0.04 |

## Expected results

- D4s v5 Linux, on-demand, 730 hours: 730 × 0.192 = **$140.16**.
- 500 GB per month of egress over the Microsoft network (`Rtn Preference: MGN`): 100 GB × $0 + 400 GB × $0.087 = **$34.80** (quickstart B2). Over the internet route: 400 × $0.08 = $32.00.
- `locations` (selectable regions) is `eastus` only: `global` and `north-america` are never listed.
