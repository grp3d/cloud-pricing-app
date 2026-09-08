# Quickstart: Validate Canvas & Pricing Improvements

This script validates the two backend-visible pieces (duration-scoped pricing, component-named
warnings, per-selection attributes) via the API, and describes the frontend smoke check for the
three canvas behaviors (connector UX, cascading resize, richer diagram detail), which are
inherently visual. Builds on `001`-`003`'s quickstart setup — run those first if the
backend/frontend aren't already running.

## Prerequisites

Same as `001`-`003`: backend running against a migrated Postgres database (no new migration in
this feature), frontend running and proxying to it.

## Validate: duration-scoped pricing and component-named warnings (User Stories 1, 3)

```bash
BASE=http://localhost:8000/api/v1
AUTH=(-H "Authorization: Bearer $TOKEN")

# 1. Build an Architecture with a Reserved-term service in one Collection and an on-demand
#    hourly service in another (reuse 001's/003's quickstart flow to create the Architecture,
#    Collections, and SKU Selections — one at pricing_term=reserved_1yr, one at on_demand).

# 2. Calculate at each duration and confirm the total changes (spec FR-001, FR-002, FR-003).
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate?duration=1_day" | jq '{duration, total_price}'
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate?duration=1_month" | jq '{duration, total_price}'
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate?duration=1_year" | jq '{duration, total_price}'
# Expect: the Reserved-term service's line item shrinks toward a 1/365 share of its full-term
# cost at duration=1_day and grows back toward its full committed cost at duration=1_year; the
# on-demand hourly service's contribution scales by day-count (1 / 31 / 365) directly.

# 3. Add a SKU Selection whose billing unit isn't in the recognized set (or exercise the
#    existing AmazonMWAA/AmazonRedshift-style unpriceable case from earlier debugging) and
#    confirm it appears in `unpriceable`, in the SAME list, each entry naming its component.
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate?duration=1_month" | jq '.unpriceable'
# Expect: every entry (whether "no price" or the new duration-unrecognized-unit reason) carries
# a non-empty `components` array naming the Collection(s), or a Data Connector description.
```

## Validate: `attributes` on an already-added SKU Selection (User Story 4)

```bash
# Reuse a Collection/SKU Selection from 003's quickstart.
curl -s "${AUTH[@]}" "$BASE/architectures/$ARCH_ID" | jq '.collections[].sku_selections[].attributes'
# Expect: a non-empty key/value map (e.g. instanceType/vcpu/memory) for each, not null/{}
# (unless that specific SKU genuinely has none, per 003's FR-003 precedent).
```

**Expected outcome**: every step above matches — durations genuinely change the total per
FR-002/003/004, warnings always name their component(s), and already-added SKU Selections carry
their descriptive attributes.

## Frontend smoke check (User Stories 1-5)

With both servers running:

1. Build an Architecture mixing a Reserved-term and an on-demand service. Change the new
   duration selector next to Calculate through 1 day / 1 month / 1 year and confirm the total
   changes each time without re-entering any pricing inputs.
2. Trigger an unpriceable/excluded warning and confirm the message names the specific
   Application Component or VPC containing that service (or, for a connector-attached service,
   names the connector) — without having to search the Architecture.
3. Select exactly two boxes on the canvas and confirm a "Connect" action becomes enabled; select
   zero, one, or three boxes and confirm it's visible but disabled. Select an existing connector
   and confirm "Remove Connector" becomes enabled. Drag directly from one box to another and
   confirm a connector is created that way too.
4. Add two similar services (e.g., different EC2 instance types) to a component and confirm its
   box shows a distinguishing detail for each.
5. Attach a service directly to a VPC (not nested inside an Application Component) and confirm
   its box shows that service. Nest a component inside a VPC, add several services to it, and
   confirm both the component's box and the VPC's box grow to keep everything visible with no
   text clipped.
