# Quickstart Validation: 020 Provider Icons and Price Change Fixes

## Prerequisites

- The local pricing data at `../_DATA-PIPELINE`, with GCP and Azure snapshots of 2026-11-02 and
  AWS up to 2026-10-05.
- The dev database migrated (`cd backend && uv run alembic upgrade head`). No new migration in
  this feature.
- Backend: `cd backend && uv run uvicorn src.main:app --reload --port 8000`.
- Frontend: `cd frontend && npm run dev`, then open http://localhost:5173.
- Automated checks:
  - backend: `cd backend && uv run pytest`, then `uv run ruff check`
  - frontend: `cd frontend && npm test`, then `npm run build`, then `npm run lint`

## A. Price Change (User Story 1)

Use a GCP architecture with one box in `us-east1`, holding one Compute Engine N2 machine
(service `6F81-5844-456A`) with 2 vCPUs and 8 GiB, 730 hours a month.

1. Calculate (Monthly). Note the total T0.
2. Change vCPUs to 4 and calculate again. Expected: Price Change = T1 − T0, not the previous
   value.
3. Change memory to 16 GiB and calculate. Expected: Price Change = T2 − T1.
4. Change memory back to 16 GiB (no real change) and calculate. Expected: Price Change stays
   T2 − T1.
5. Change vCPUs to 8. Expected: the "updated since last pricing" notice appears. Switch Duration
   to Yearly and calculate.
   - Expected: Price Change = the new yearly total − (the previous contents, 4 vCPUs and 16 GiB,
     priced yearly in us-east1).
   - Check: calculate the previous contents yearly by hand from the price data, cores × core rate
     + GiB × RAM rate, × 12 months. It must match.
6. On an Azure architecture with one Linux VM, calculate, switch the VM to Windows, calculate.
   Expected: Price Change = new − old.
7. On an AWS architecture with a box in `eu-west-1`, calculate Monthly, change a quantity, switch
   to Yearly and calculate. Expected: the comparison prices the previous contents at eu-west-1
   rates, not us-east-1. Check against the line item's yearly price.

## B. Last calculations from before this update

1. In the browser's dev tools, take a GCP architecture's stored last calculation and remove
   `version`, `region` and `provider_options` from it. This simulates one stored by v0.0.2.
2. Calculate with no change. Expected: Price Change keeps its value, and the "updated since last
   pricing" notice does not appear.
3. Switch Duration and calculate. Expected: Price Change shows no value, with
   "Not available: previous calculation from prior version is unreliable".
4. Switch Duration back and calculate. Expected: a correct Price Change (a version 2 baseline is
   now stored).
5. Repeat step 1 on an AWS architecture, then switch Duration. Expected: a Price Change value, as
   in v0.0.2. No "Not available" note.

## C. Icons (User Story 2)

1. **GCP:** add these services:
   - a Compute Engine machine
   - a Compute Engine persistent disk
   - a Cloud Storage bucket
   - a Cloud SQL instance
   - Cloud Load Balancing
   - an external IP address

   Expected: the Compute Engine, Persistent Disk, Cloud Storage, Cloud SQL, Cloud Load Balancing
   and External IP icons respectively.
2. **Azure:** add these services:
   - a Linux VM
   - a managed disk
   - Blob storage
   - Azure SQL Database
   - a load balancer
   - a public IP address

   Expected: each shows its own Azure icon, and the managed disk shows the Disks icon, not the
   VM's.
3. **GCP fallback:** add a marketplace service, for example search "OpenLogic". Expected: a tile
   with the Google Cloud logo and the service's name, cut to at most three lines. Hovering shows
   the full name.
4. **Several fallbacks:** add two different marketplace services. Expected: each tile shows its
   own name.
5. **Themes:** switch to dark mode, then back. Expected: every icon, logo and name stays clearly
   visible.
6. **AWS:** open an existing AWS architecture. Expected: identical to v0.0.2, including its
   fallback icon.
7. **Existing layouts:** open a GCP or Azure architecture created in v0.0.2 with icons moved by
   hand. Expected: same positions and sizes, new icons.
8. **Generator report:** run
   `cd backend && uv run python scripts/generate_provider_service_icon_map.py --provider gcp --icons ../../images-web/gcp_architecture_icons`,
   then the same with `--provider azure` and the Azure folder. Expected:
   - the report's "categorized services without an icon" list is empty for both (SC-003)
   - re-running produces no file changes

## D. Regression

- All backend and frontend tests pass, and lint, the build and the API-type check are clean.
- The pop-out diagram shows the same icons as the main one.
- Export and import a GCP architecture. Expected: icons resolve the same way after import.
