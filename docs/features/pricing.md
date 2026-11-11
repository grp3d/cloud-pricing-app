# Pricing

Every price comes from the provider's published price list, in USD, exactly as published. A
price that can't be found is shown as such: never as zero, never estimated.

## Setting up a service

In the **Service** tab, a service has:

- **Price type**:
  - AWS: on demand, or Reserved for 1 or 3 years with no, partial or all upfront.
  - GCP: on demand, or committed use for 1 or 3 years.
  - Azure: on demand, savings plan for 1 or 3 years, or reservation for 1 or 3 years.
  For GCP and Azure only the types the SKU publishes are offered; AWS offers all three.
- **Usage quantity**, in the SKU's own unit, which is shown next to the field. A Reserved AWS
  selection doesn't use a quantity (see [how prices are worked out](#how-prices-are-worked-out)).
- **Provider fields** where they apply: vCPU count and memory for a GCP machine (priced from its
  vCPU and memory SKUs together), and the operating system (Linux or Windows) for an Azure VM.
  Five kinds of service get fields tuned to them: virtual machines, block storage, object
  storage, data transfer and managed databases.

**Save** is dark blue when something differs from the saved service, and light blue otherwise;
saving keeps the service open in the Service tab. The search result's arrow adds a service with
default values without opening it first.

## Calculate

- Choose a duration, **1 day**, **1 month** or **1 year**, and press **Calculate**. The
  durations are fixed at 1, 31 and 365 days.
- **Calculate** is dark blue when the price is out of date or the architecture has never been
  priced, and light blue otherwise. It is always clickable.
- An architecture with services and no stored result is calculated automatically when it opens.
- After any edit that can change a price, the notice "Architecture has been updated since last
  pricing" shows until the next calculation.
- Every calculation uses one pricing snapshot for the whole result, and shows its date and
  revision (see [providers and pricing data](providers-and-pricing-data.md)).

## How prices are worked out

- **Usage pricing** (on demand, savings plan, committed use): the quantity is converted to a
  31-day month by its unit (per hour, per month, per request and so on), priced, then scaled to
  the duration.
- **Tiers**: a tiered price is graduated, for every provider. With tiers 0–10, 10–20 and
  20–1000, a quantity of 40 is 10 at the first rate, 10 at the second and 20 at the third. The
  price list shows how each part was priced.
- **Reserved and upfront** (AWS reserved, Azure reservation): the recurring rate bills for every
  hour of the duration, whatever the quantity, plus the duration's share of any upfront fee. An
  Azure reservation is a whole-term fee, so it is priced as all upfront.
- A **data transfer** service on a connector is priced in the "from" collection's region.
- A SKU with no price, or whose unit can't be classified, is listed under "Some SKUs could not
  be priced and are excluded from the total", with the reason and the collection it belongs to.
- VPCs that no connector links produce a warning that doesn't block the result.

## The result

The **Pricing** tab shows:

- the **total** for the duration;
- **Price Change** since the previous calculation of this architecture;
- the **Price per SKU** list, grouped and subtotaled by region. Each line shows the service (a
  GCP or Azure line by its readable name and description, with the codes muted), its price type
  and its price. A word-wrap toggle beside the heading wraps long lines, for the current session;
- the excluded SKUs and warnings, each naming the collection or connector it came from;
- the snapshot date and revision.

Each architecture keeps its own last result, in the browser: switching architectures shows that
architecture's result straight away, with the duration it was computed for, and never another
architecture's.

## Price Change

- Any edit that can change a price counts: the service, SKU, price type, purchase option,
  quantity, region, and provider fields.
- If only the contents changed, Price Change is the new total minus the previous one.
- If the duration changed, the previous contents are priced again at the new duration first, so
  the change compares like with like.
- A previous result saved by a version before v0.1.0 lacks some of those settings. For a GCP or
  Azure architecture whose duration changed, Price Change then shows "Not available: previous
  calculation from prior version is unreliable" instead of a figure that could be wrong.

## Specs

[001](../../specs/001-assemble-price-aws-architecture/spec.md),
[003](../../specs/003-service-selection-improvements/spec.md),
[004](../../specs/004-canvas-pricing-improvements/spec.md),
[006](../../specs/006-fix-reserved-pricing/spec.md),
[008](../../specs/008-ui-updates-corrections/spec.md),
[009](../../specs/009-ui-fixes-next-iteration/spec.md),
[010](../../specs/010-multi-region-support/spec.md) (US7),
[015](../../specs/015-canvas-service-icons/spec.md) (US4, US5),
[019](../../specs/019-gcp-azure-providers-trends/spec.md) (US1),
[020](../../specs/020-provider-icons-connector-fixes/spec.md) (US1),
[021](../../specs/021-workspace-layout-redesign/spec.md) (US5, US7).
