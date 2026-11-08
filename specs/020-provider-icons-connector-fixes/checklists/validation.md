# Validation Notes: 020 Provider Icons and Price Change Fixes

## T001 Baseline (branch `020-provider-icons-connector-fixes` at `d5a5436`)

| Check | Result |
|---|---|
| backend `uv run pytest` | 897 passed |
| backend `uv run ruff check` | All checks passed |
| frontend `npm test` | 42 files, 351 tests passed |
| frontend `npm run build` | built (chunk-size warning only, as before) |
| frontend `npm run lint` | 0 errors, 7 warnings (all pre-existing) |

## T014 Quickstart A and B (User Story 1), 2026-11-06

**How it was run.** Quickstart A ran through the API against the real pricing data
(`PRICING_DATA_URI=file://…/_DATA-PIPELINE`: GCP and Azure 2026-11-02, AWS 2026-10-05), on the
test database, using a throwaway test that was deleted afterwards. The frontend decisions
(comparison key, legacy rule, "Not available", what is sent to the snapshot endpoint) are
covered by the automated page tests in `WorkspacePage.pricing.test.tsx` (T013). The browser
walk-through, including quickstart B's dev-tools edit of a stored baseline, is still to do and is
planned for the same session as T025's visual checks.

Quantities are hours per day (24 h/day). A month is 31 days and a year 365.

| Step | Result | Expected | Pass |
|---|---|---|---|
| A1 | GCP N2, us-east1, 2 vCPUs / 8 GiB, monthly: T0 = $72.255792 | (2 × 0.031611 + 8 × 0.004237) × 24 × 31 | ✓ |
| A2 | 4 vCPUs: T1 = $119.29296; T1 − T0 = $47.037168 | (4 × 0.031611 + 8 × 0.004237) × 744 | ✓ |
| A3 | 16 GiB: T2 = $144.511584; T2 − T1 = $25.218624 | (4 × 0.031611 + 16 × 0.004237) × 744 | ✓ |
| A4 | Same value put back counts as unchanged | unit and page tests (T004, T013) | ✓ |
| A5 | Previous contents (4 / 16) re-priced yearly by the snapshot endpoint = **$1,701.50736**; new yearly (8 / 16) = $2,809.1568; Price Change = $1,107.64944 | hand check: (4 × 0.031611 + 16 × 0.004237) × 24 × 365 = **$1,701.50736** | ✓ |
| A6 | Azure D4s v5, eastus, monthly: Linux $142.848, Windows $279.744, Price Change $136.896 | 744 × 0.192 and 744 × 0.376 | ✓ |
| A7 | AWS eu-west-1 EC2 `22857BA35WWDDHD7`, yearly: architecture $1,853.616, snapshot with region $1,853.616 | 0.2116 × 24 × 365 = $1,853.616 (v0.0.2 priced it in us-east-1, where the SKU isn't found) | ✓ |
| B2 | Legacy baseline, no change: Price Change kept, no "updated" notice | page test (T013) | ✓ (automated) |
| B3 | Legacy GCP baseline + Duration switch: "Not available: previous calculation from prior version is unreliable", no snapshot call | page test (T013) | ✓ (automated) |
| B4 | A version 2 baseline is stored after B3 | page test checks the stored baseline | ✓ (automated) |
| B5 | Legacy AWS baseline + Duration switch: re-priced as before | page test (T013) | ✓ (automated) |
| Browser walk-through of A and B | | | to do with T025 |

## User Story 2: icon generator runs (T019, T020), 2026-11-06

Against `_DATA-PIPELINE` (GCP and Azure snapshots 2026-11-02 r1).

| | GCP | Azure |
|---|---|---|
| Services in the snapshot | 1,748 | 188 |
| Exact name matches | 60 | 70 |
| Reviewed overrides (service) | 39 | 46 |
| Reviewed overrides (more specific icons inside a service) | 26 (Compute Engine, Networking) | 12 (Storage, Virtual Network) |
| Services with an icon | 99 (5.7%) | 116 (61.7%) |
| Fallback: first-party / marketplace | 76 / 1,573 | 72 / 0 |
| **Categorized services without an icon (SC-003)** | **0** | **0** |
| `WARNING` lines (an override matching no product) | 0 | 0 |
| SVGs shipped | 91 (364 KB) | 123 (516 KB) |
| Second run changes nothing (FR-010) | ✓ (same hash) | ✓ (same hash) |

Spot checks from quickstart C, via the resolver against the real maps (`serviceIcons.test.ts`,
`ServiceIconList.test.tsx`):

| Selection | Icon |
|---|---|
| GCP Compute Engine machine (`Compute > GCE > VMs On Demand`) | Compute-Engine |
| GCP Compute Engine disk (`Compute > Persistent Disk > …`) | Persistent-Disk |
| GCP external IP (`Network > Cloud VPN > IP Address`, `Compute > GCE > Network Other`) | Cloud-External-IP-Addresses |
| GCP Cloud Storage, Cloud SQL | Cloud-Storage, Cloud-SQL |
| GCP Networking load balancing (`Network > Cloud LB`), NAT | Cloud-Load-Balancing, Cloud-NAT |
| Azure Virtual Machines | Virtual-Machine |
| Azure Storage, managed disks (`Premium SSD Managed Disks`) | Disks |
| Azure Storage, blob (`General Block Blob v2`) | Storage-Accounts |
| Azure Virtual Network, `IP Addresses` | Public-IP-Addresses |
| Azure Load Balancer, SQL Database, Bandwidth | Load-Balancers, SQL-Database, Azure-Data-Transfer |
| GCP marketplace service | fallback tile: Google Cloud logo and name |

## T028 Final checks, 2026-11-06

| Check | T001 | Now |
|---|---|---|
| backend `uv run pytest` | 897 passed | **937 passed** |
| backend `uv run ruff check` | clean | clean |
| frontend `npm test` | 42 files, 351 passed | **44 files, 408 passed** |
| frontend `npm run build` | built | built |
| frontend `npm run lint` | 0 errors, 7 warnings | 0 errors, 7 warnings (the same pre-existing ones) |
| API types match the backend schema | – | ✓ (regenerated output identical) |
| Account-ID grep (CI rule, including new files) | – | no matches |

## Browser checks (T025, T028), 2026-11-08

**How they were run.** Playwright end-to-end tests in headless Chromium (`frontend/e2e/`,
`npm run test:e2e`), against the app's own backend with a fresh database and the committed
pricing fixture (`backend/tests/fixtures/pricing_parquet`). The fixture has the same N2, Azure
D4s v5 and AWS eu-west-1 rates as the real data, so quickstart A's figures are unchanged. The
full suite ran three times in a row: 36 passed, none flaky.

**Not against the real data.** The fixture has none of these services:
- GCP Cloud Load Balancing and external IP
- Azure SQL Database, load balancer and public IP
- any GCP marketplace service

Those icons are covered by the resolver tests against the real maps (table above). The fallback
tiles were shown by rewriting two selections in the architecture the page loads; the tile is
drawn entirely by the frontend.

| Quickstart | Test | Result |
|---|---|---|
| A1–A5 | GCP N2: 72.26 → 119.29 (+47.04) → 144.51 (+25.22), same value saved again keeps +25.22 with no notice, 8 vCPUs then Yearly: 2,809.16 (+1,107.65) | ✓ |
| A6 | Azure Linux → Windows: 142.85 → 279.74 (+136.90) | ✓ |
| A7 | AWS eu-west-1, 24 → 12 h/day then Yearly: 926.81, Price Change −926.81 (eu-west-1 rates; us-east-1 would give +926.81) | ✓ |
| B1–B4 | Baseline rewritten as v0.0.2 stored it: no notice, Price Change kept; Yearly gives "Not available" (also after a reload); back to Monthly gives 0.00 and a version 2 baseline | ✓ |
| B5 | Same on AWS: a Price Change value, no "Not available" | ✓ |
| C1 | Compute-Engine, Persistent-Disk, Cloud-Storage, Cloud-SQL; no AWS icon | ✓ |
| C2 | Virtual-Machine, Disks, Storage-Accounts, Azure-Database-PostgreSQL-Server, Azure-Data-Transfer | ✓ |
| C3–C4 | Two fallback tiles, each with its own name and the Google Cloud logo, same size as an icon, the long name cut to three whole lines, full name on hover | ✓ after two fixes (below) |
| C5 | Light and dark screenshots of every canvas, checked by eye: icons, logos and names clearly visible | ✓ |
| C6 | AWS: Amazon-EC2, and the generic AWS logo with no name for an unknown service | ✓ |
| C7 | Hand-placed icon keeps (130, 70); resized box keeps its size | ✓ |
| D | Pop-out shows the same icons; a GCP architecture exported and imported through the Admin API shows the same icons | ✓ |

**Fixed during these checks (020 bugs):**
- Hovering a fallback tile showed only the service code and SKU, not the name (FR-009). The
  tooltip and accessible name now start with the full name. The unit test claimed to check this
  but only looked for the service code; it now checks the full accessible name.
- The fallback tile's third line was cut in half: under the 22 px logo badge only 30 px were
  left for 11 px text. Now a 16 px badge (14 px logo) and 10 px text on 12 px lines, so three
  whole lines fit (research R7 updated).

**Found, not fixed (not caused by 020):** a box resized to about 420 × 320 and then moved is
saved correctly, but after a reload React Flow keeps it at `visibility: hidden`, so it disappears
from the canvas. Reproduced through the UI. Smaller boxes, or the same size at (0, 0), show. Kept
as a `test.fixme` in `e2e/icons.spec.ts`.

**Checks after these changes:** frontend `npm test` 44 files, 408 passed; `npm run build` built;
`npm run lint` 0 errors, the same 7 warnings. No backend file changed since the T028 run above
(937 passed, ruff clean).
