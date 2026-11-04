# Quickstart Validation: 019-gcp-azure-providers-trends

Results of running [quickstart.md](../quickstart.md) against the local pipeline root. Each later
quickstart run (sections C to F) adds its own section here.

## Section B: GCP and Azure in the workspace (US1), 2026-11-04

**Setup**:

- Pipeline root: `../_DATA-PIPELINE` (`file://`).
  - AWS: snapshot 2026-10-05.
  - Azure: 2026-11-02 r1, regions `eastus`, `eastus2`, `westus`, `westus2`, plus `global` and `north-america`.
  - GCP: 2026-11-02 r1, regions `us-east1`, `us-east4`, `us-west1`, `us-west2`, plus `global`.
- Database: `cloud_pricing_test` at migration head.
- Run at API level through the app (httpx against the ASGI app), in the same order as the quickstart steps.
- Each expected price was queried directly from the snapshot's Parquet files listed in its manifest, not taken from the app.
- The UI steps (hover text, editor fields, tier and component display) are covered by the frontend unit tests (T057). They are not clicked through in a browser here.

| Step | Result | Evidence |
|---|---|---|
| B1 | Pass | `GET /providers`: GCP and Azure are both `active` and `current`, with snapshot 2026-11-02. AWS is `active` and `stale` (2026-10-05 is 30 days old, past the 14-day limit). The hover text is `providerHint` (tested in `ProviderArchitecturePanel.test.tsx`). |
| B2.1 | Pass | Search: kind `vm`, query `D4s v5`. Item `DZH318Z08M9W/004T/db8c0962-…`. Its reference row (`arm_sku_name = Standard_D4s_v5`, Consumption, `Virtual Machines Dsv5 Series`) is $0.192/h. 24 h/day for 31 days costs $142.848, which equals rate × 744. |
| B2.2 | Pass | P10 LRS disk (Premium SSD Managed Disks): $19.71 for the month. `Rtn Preference: MGN` egress on a connector at 620 GB a month splits into two tiers: 100 GB at $0 and 520 GB at $0.087, total $45.24. |
| B3 | Pass | n2-standard-4: core `BB77-5FDA-69D9` at $0.031611 and RAM `5B01-D157-A097` at $0.004237. 4 × core + 16 × RAM = $0.194236/h. The month costs $144.511584, split into vCPUs $94.074336 and Memory $50.437248. |
| B4 | Pass | AWS `us-west-2` internet egress, SKU `5M4327XEUKBBTWAT`, 20,491 GB a month: two tier parts, 10,240 GB at $0.09 and 10,251 GB at $0.085, total $1,792.935. |
| B5 | Pass | Azure service `Virtual Machines Licenses`: 2,347 items, all `global`. GCP query `Licensing Fee`: 3,522 items, all `global`. |
| B6 | Pass | A copy of the root with GCP's newest manifest set to `failed`. GCP is inactive (`failed`, "snapshot rejected"), and a GCP search returns 503 with `provider: gcp` and that reason. Azure search and calculation, and AWS search, still return 200. |
| B7 | Pass | Exported the Azure architecture and imported it under a new user. It imported (1 of 1), and its total matched exactly: $207.798 both times. |

**Deviations from the written steps**:

- **B2.1 quantity**: the step says "730 hours". Quantities are a daily amount scaled over the 31-day month, so 24 h/day was used, which is 744 hours.
- **B2.2 and B4 quantities**: "500 GB" and "20,480 GB" a month can't be entered exactly as a daily amount with 4 decimals. 20 GB/day (620 GB a month) and 661 GB/day (20,491 GB a month) were used instead, which still show the tier split the steps describe.
- **B5, Azure**: the data has no Azure support plans, so global licences were used, as in the fixture.
- **B6 setup**: a directory of symlinks was refused by the data store. The store resolves paths and refuses anything outside the root, which is correct behavior. A full copy of the root was used instead.
