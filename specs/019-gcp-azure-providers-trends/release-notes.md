# Release notes: v0.0.2

Feature 019: GCP and Azure providers, the Trends page, settings saved to the account, and
diagram arrows.

## What's new

- **GCP and Azure pricing.** Build and price GCP and Azure architectures the same way as AWS:
  catalog search by kind of service, provider-specific price types (Azure savings plans, GCP
  committed use), Azure Windows or Linux VMs, and GCP machines priced as vCPUs plus memory.
  Global and multi-regional prices are labelled in search.
- **Each provider is enabled on its own.** A provider is active only when it has a usable pricing
  snapshot. Its button says why when it isn't. One provider's missing or rejected data never
  affects the others. A snapshot older than `SNAPSHOT_STALE_DAYS` (default 14) is shown as stale
  but stays active.
- **Trends page.** The Trends tab now opens:
  - **SKUs changed per week**: for each provider, how many SKUs' on-demand list price went up
    and how many went down between consecutive weekly snapshots, over up to 52 weeks, by region
    and category (compute, storage, database, networking). Only SKUs with a non-zero price in
    both weeks are compared. A week with nothing compared shows "no data", never 0.
  - **Biggest movers**: the 3 largest % increases and decreases for one provider, category,
    regions and period (1, 4, 13 or 52 weeks), with start and end prices as published.
  - Tiered prices are compared on their first non-zero tier, so a free first tier doesn't hide a
    change.
- **Settings follow the user.** Trends selections, column widths, collapsed columns and the last
  provider picked are saved to the account and restored on any device. A change applies at once;
  a failed save is retried in the background.
- **Diagram arrows.** A connector can be a plain line, one-way or two-way, and a one-way arrow can
  be reversed. Arrows are kept by export, import and copying, and never change a price.
- **Admin tab.** Snapshot, latest run and issues are shown per provider, plus each provider's
  Trends history (weeks built, gaps, backfill state).

## Changes to existing behaviour

- **AWS tiered prices are fixed, so some existing totals change.** Before, a tiered AWS SKU was
  priced at whichever tier the price list returned first. Now the quantity is split across the
  published tiers, each part at its own rate (graduated tiers), and the line shows the
  breakdown. This mostly affects data transfer, plus S3, CloudWatch, SES and some AI services
  (308 of about 171,000 on-demand price keys in one us-west-2 snapshot). **The new totals are the
  correct ones.** Tiers apply per line, not to usage pooled across lines as a real bill does.
- **Existing connectors keep their arrowhead.** Since 0.0.1 every connector was drawn with an
  arrowhead at its "to" end. Migration 0008 sets existing connectors to one-way, so diagrams look
  the same. New connectors start as plain lines. Export files from 0.0.1 import with one-way
  arrows.
- **Browser settings move to the account once.** Column widths and collapsed columns saved in a
  browser by 0.0.1 are copied to the account on the first load, with any values already on the
  account winning. After that the browser copy is ignored. Settings tied to one architecture
  (box positions, connector bends and sides, zoom, icon layout, last calculation) stay in the
  browser.
- **API additions.** `/me/preferences`, `/trends/series`, `/trends/movers` and
  `PATCH /connectors/{id}` are new. Catalog and region endpoints take a `provider`. The
  pricing-unavailable (503) body now names the provider and the reason.

## GCP and Azure in production

GCP and Azure stay **disabled in production**, shown as "no snapshot available", until the
pricing pipeline's GCP and Azure production rollout (pipeline 004 quickstart Part C, from step C2)
is done. Nothing in the app needs to change when it is: each provider enables itself once its
first snapshot appears in the data source. Their Trends charts need at least two weekly
snapshots, so they show "not enough history" for the first week after that.

## Upgrading

- **Database**: migrations 0006, 0007 and 0008 run on start (`db-init`), as before. They add the
  preferences, service categories and connector arrow data, and seed the service categories.
  No existing data is removed.
- **Trends history**: the backend builds it at startup and after each new snapshot, in the new
  `pricing-history` volume (`PRICING_HISTORY_DIR=/var/lib/app/pricing-history`). It survives
  container restarts and is rebuilt from the snapshots on a new instance. While it builds, the
  Trends page shows the weeks built so far.
- **Memory**: the first history build is the heaviest job the app runs. Locally it built 7 weeks
  of AWS history in 3.1 s, with the process peaking at about 1.2 GB. On the 2 GiB instance, let
  it finish while the app is quiet, or lower `DUCKDB_THREADS`. A build from S3 has not been
  measured yet.
- **New settings** (all optional): `SNAPSHOT_STALE_DAYS`, `PRICING_HISTORY_DIR`,
  `PRICE_HISTORY_ENABLED`. See `docs/configuration.md`.

## Not in this release

- **Branching connectors** (one-to-many, many-to-one) are deferred to a later release. The
  database table for them exists but is unused, and the styles aren't offered in the editor.
- Price Trend (median weekly change) and Cumulative Change charts: list prices change too
  rarely for them to show anything (0 to 4 changes a week among up to 708,000 AWS SKUs).
