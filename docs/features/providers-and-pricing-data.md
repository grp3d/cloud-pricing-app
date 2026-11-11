# Providers and pricing data

The app prices **AWS**, **GCP** and **Azure**. Each architecture belongs to one provider, and
everything works the same way for all three: creating and sharing architectures, collections,
connectors, search and calculation. Prices are never compared across providers.

## Where prices come from

The price lists come from the separate pipeline,
[cloud-pricing-data-retrieval](https://github.com/grp3d/cloud-pricing-data-retrieval), which
publishes a **snapshot** of each provider's price list, normally weekly. The app reads them,
read-only, from a local folder or from S3 (`PRICING_DATA_URI`).

- Snapshots are found only through the pipeline's manifests: the newest succeeded one, or a date
  pinned with `ACTIVE_SNAPSHOT_DATE`.
- Each provider has one **active snapshot**, and every calculation uses it for the whole result.
  The result shows its date and revision; a corrected revision is never shown under the same
  label.
- The app checks for a newer snapshot at startup and then every 5 minutes (and when an Admin
  presses **Check now**). A newer usable snapshot replaces the active one all at once. If a new
  one is incomplete or fails its checks, the current one stays active and the Admin tab says
  why.

The details (manifests, the S3 cache, converting old data) are in
[configuration.md](../configuration.md#pricing-data).

## Provider status

Each provider's status is worked out on its own; one provider's problem never affects another.

| Status | Meaning | Usable |
|---|---|---|
| current | the active snapshot is the newest | yes |
| partial | active, but the newest pipeline run is newer and didn't fully succeed | yes |
| stale | the active snapshot is older than 14 days (`SNAPSHOT_STALE_DAYS`) | yes |
| failed | snapshots were published, but none is usable | no |
| none | nothing has been published yet | no |

A provider that isn't usable is disabled, with the reason. The app still starts, logins and
saved architectures still work, and its pricing requests return "pricing data unavailable" until
a snapshot appears.

## What each provider adds

- **Regions**: each provider's regions come from its data, with readable names. The search also
  includes SKUs priced only globally.
- **Names**: GCP and Azure SKUs are identified by a readable service name and description. The
  hover text, the Service tab and the price list show it first, with the codes muted beside it
  (the canvas boxes don't yet). Azure descriptions drop words already in the service name.
- **Price types and fields**: see [pricing](pricing.md#setting-up-a-service).
- **Icons**: each provider's own official icon set on the canvas. A GCP or Azure service with no
  matching icon shows a labelled provider tile; an AWS one shows a generic AWS icon and is listed
  in the Admin tab's Issues table (GCP and Azure aren't checked there yet).

## Categories

Services are grouped into **compute**, **storage**, **database** and **networking** by rules
seeded in the database (migration `0007`), matched on each provider's own grouping fields. A
service no rule matches is uncategorized and appears only under "all categories". The categories
are used by [Trends](trends.md).

## Specs

[016](../../specs/016-canvas-icon-layout/spec.md) (US4, US5),
[018](../../specs/018-app-cloud-deployment/spec.md) (US1, US5),
[019](../../specs/019-gcp-azure-providers-trends/spec.md) (US1),
[020](../../specs/020-provider-icons-connector-fixes/spec.md) (US2),
[021](../../specs/021-workspace-layout-redesign/spec.md) (US7).
