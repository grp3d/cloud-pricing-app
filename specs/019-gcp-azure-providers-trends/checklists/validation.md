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

## SC-004: Trends page load with the default selection (T090), 2026-11-04

**Setup**: the same local pipeline root. Each provider's history was built first into a new
folder (AWS: 6 week pairs, 2026-08-30 to 2026-10-05, built in 3.1 s; Azure and GCP: one snapshot
each, so no pairs yet). The requests the page makes were then timed in-process, in the order
the browser makes them: providers and preferences together, then each active provider's
regions, then the chart series (all three providers, all regions, all categories) and the
movers (first provider, all categories, all regions, 52 weeks) together. Browser rendering
time is not included.

| Load | Time | Result |
|---|---|---|
| First (fresh app state) | 1.50 s | Pass (< 3 s) |
| Second | 1.26 s | Pass |
| Third | 1.37 s | Pass |

What the page got: the AWS series is `ok` with 6 points; GCP and Azure are
`not_enough_history`. The AWS movers compare 2026-08-30 r1 with 2026-10-05 r1 (6 weeks of
history, shorter than the 52-week period): 3 increases (AWS IoT LoRaWAN messages, +160.87%, in
three regions, each a separate entry) and 2 decreases (an Amazon Bedrock API call price,
−55.56%, in two regions).

## Section E: Preferences follow the user (US4, T095), 2026-11-04

**Setup**: the test database, one new named user signed in through `POST /auth/login` from two
separate HTTP clients ("browser A" and "browser B"), at API level through the app. The browser
side (what the page sends, the one-time move, retries) is covered by the frontend unit tests
named below. It was not clicked through in two real browsers.

| Step | Result | Evidence |
|---|---|---|
| E1 | Pass | Browser A saved Trends charts (AWS us-east-1, compute), movers (AWS, storage, 13 weeks), column 2 at 412 px and last provider GCP: `PATCH /me/preferences` 200. |
| E2 | Pass | Browser B, signed in separately, got exactly the same `trends` and `workspace` sections (SC-006). |
| E3 | Pass | Reset on the charts section (`trends.charts: null`, as `TrendsPage` sends it) left only the movers section, and the workspace untouched, on the next load. Reset independence on the page: `ChartSelectors.test.tsx`, `MoversPanel.test.tsx`. |
| E4 | Pass | The one-time move as the page sends it (`workspace` + `migrated_from_browser: true`): `GET /me/preferences` shows `migrated_from_browser: true` and the moved values. Reading old browser values, the account's values winning, sending once and ignoring browser values afterwards: `preferences.test.ts`, `columnWidths.test.ts`, `columnCollapse.test.ts`. |
| E5 | Pass (unit test) | A failed save is queued and retried with backoff without an error reaching the page; the change applies at once: `preferences.test.ts` ("queues a failed save and retries with backoff, never throwing"). The backend was not stopped by hand. |

## Full quickstart, sections A to F (T111), 2026-11-05

The same local pipeline root and test database, at API level through the app, after all of
US1 to US5 (arrows) were built. Branching connectors (phase 9) are deferred, so F2, F3 and the
branch half of F4 were not run.

| Step | Result | Evidence |
|---|---|---|
| A | Pass | Backend 897 tests and ruff check pass. Frontend: build, 351 tests and lint (0 errors) pass. API types: regenerated from the app's OpenAPI schema (`check-api-types` needs a server on port 8000), which found one stale doc comment, the import default for `arrow_style` (`@default one_way`), now committed. |
| B1–B5, B7 | Pass | Re-run: the same values as the section B table above. |
| B6 | Pass | Re-run on a full copy of the root with GCP's manifest set to `failed`: GCP inactive ("snapshot rejected"), its search 503 naming GCP; Azure search and calculate (total $450.864) and AWS search 200. |
| C1 | Pass | Defaults: one series per active provider (AWS `ok`; GCP and Azure `not_enough_history`), metric `skus_changed` only. |
| C2 | Pass | AWS, us-east-1 and us-west-2, compute: one series of 6 points; the newest (2026-10-05) has 0 up and 0 down of 156,953 compared, 92,922 excluded, and every hover field. |
| C3 | Pass | GCP and Azure (one snapshot each): `not_enough_history`. |
| C4 | Pass | From an empty history folder, polled during the backfill: `building` with 0, 1, 2 and 3 of 6 weeks. Run again after it finished: no pair rebuilt and no snapshot fetched (the same `built_at` and price list). |
| C5 | Pass | Newest week (2026-09-28 r1 → 2026-10-05 r1, all regions and categories) counted by hand from the raw `price_fact` files: 708,107 compared, 4 up, 0 down. The chart has exactly the same. |
| D1 | Pass | AWS, compute, all regions, 52 weeks: "No price changes in this period" (2026-08-30 r1 → 2026-10-05 r1, 6 weeks). |
| D2 | Pass | The top entry over all categories (AWS IoT, eu-west-1, SKU `VASZ89G874NK4XRM`) checked against its price in every weekly snapshot: absent until 2026-09-20, then 0.0000023, and 0.000006 on 2026-10-05, so +160.87%. The list shows exactly that (SC-004a). |
| E | Pass | See section E above. |
| F1 | Pass | A connector with a t3.medium selection: none → one-way → two-way → one-way → reversed. The total is $64.48 every time (SC-007). |
| F2, F3 | Not run | Branching connectors are deferred. |
| F4 | Pass (styles) | One-way reversed is kept after a reload, in the export file, and in the copy imported under another user. |
