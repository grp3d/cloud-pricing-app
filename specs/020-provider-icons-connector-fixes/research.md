# Research: Provider Icons and Price Change Fixes (020)

Findings from reading the current code (branch base `7bcde50`, v0.0.2) and the local pricing data
(`_DATA-PIPELINE`: GCP and Azure snapshots of 2026-11-02, AWS up to 2026-10-05).

## R1 - Why Price Change misses GCP and Azure edits

**Finding.** `frontend/src/lib/priceChange.ts` decides "did the contents change?" with a key of
`service_code, sku, pricing_term, purchase_option, usage_quantity`. A selection's
`provider_options` (GCP `gcp_machine`: `vcpus`, `memory_gib`, `ram_sku`; Azure `azure_vm`: `os`)
and its region aren't in the key. `WorkspacePage.tsx` builds the baseline and the "updated since
last pricing" comparison (`pricedContentsEqual`) from the same five fields, the latter plus
region. Hours per day changes `usage_quantity`, which is why that edit works.

**Decision.** Add `provider_options` and `region` to the Price Change comparison. Add
`provider_options` to the "updated since last pricing" comparison, which already has the region.
Options are compared in a canonical form (sorted keys, values as the API returns them), so a
value that is edited and then put back counts as unchanged.

**Why region too.** Moving a service to a box in another region (feature 016) changes its price.
Today Price Change treats that as unchanged, which is the same kind of bug. FR-001 covers "any
other setting" that changes a price.

**Alternatives considered.** Comparing totals instead of contents (rejected: that would change
the "nothing changed → keep the displayed value" rule from 009).

## R2 - Why the Duration-switch path is wrong for GCP and Azure

**Finding.** When the Duration changes, the page re-prices the previous selections through
`POST /catalog/calculate-snapshot`. That request carries no provider, no region and no
`provider_options`. `build_transient_architecture` (`backend/src/services/price_calculation.py`)
puts every selection in one throwaway collection in `AWS_PRICING_REGION` (us-east-1) on an
architecture whose provider is unset, which `get_provider` treats as AWS. So:

- On a GCP or Azure architecture, the previous contents are looked up in AWS's tables. They
  aren't found, so the comparison total is wrong.
- On an AWS architecture with boxes outside us-east-1, the previous contents are priced at
  us-east-1 rates. The code comment notes this was a known limitation from 010.
- A GCP machine would be priced as cores only, without its RAM.

This conclusion comes from reading the code; it was not reproduced end to end.

**Decision.** Make the snapshot request carry everything a price depends on:

- `provider` on the request (the architecture's provider; missing = `aws`, as elsewhere).
- `region` and `provider_options` on each selection (missing region = today's
  `AWS_PRICING_REGION`, missing options = none).

`build_transient_architecture` sets the architecture's provider and puts selections into one
throwaway collection per region. Everything else uses the shared pricing code path, as today.
The fields are optional, so an older client keeps today's behaviour.

**Consequence.** After a Duration switch, an AWS architecture with boxes outside us-east-1 now
gets a correct Price Change rather than one priced at us-east-1 rates. This changes AWS results
in that one case, for the better. The spec's assumption that "AWS results stay the same" is
updated to say so.

**Alternatives considered.** Re-pricing on the frontend by scaling the old total by the Duration
ratio (rejected in 009: Price Change must come from a real calculation, Principle I).

## R3 - Last calculations stored before this feature

**Finding.** The last calculation is kept per architecture in the browser
(`priorCalculation.ts`, `architecturePricingResults.ts`), with a type guard that drops unreadable
values. Stored entries have no region or `provider_options`.

**Decision.** Store a `version: 2` baseline with region and options on each selection. Read
version 1 (no `version` field) as a *legacy* baseline:

- Duration unchanged: Price Change = new total − previous total (always correct).
- Nothing changed: keep the displayed value (as today). A legacy entry is compared on the old
  five fields only, so the upgrade alone never makes contents look changed.
- Duration changed:
  - AWS architecture: re-priced as today (us-east-1, no options), as FR-005 says "handled exactly
    as today".
  - GCP or Azure architecture: Price Change shows no value, with the note "Not available:
    previous calculation from prior version is unreliable".
- A version 2 baseline is stored after every calculation, so the next comparison is exact.

The same legacy rule applies to the stored "updated since last pricing" contents: a legacy entry
is compared without options, so the notice doesn't appear just because of the upgrade.

**Note on scope.** The spec's FR-005 says "a GCP machine or Azure VM". A legacy baseline on any
GCP or Azure architecture also lacks regions, and those providers have no default region to fall
back to, so the rule is widened to every GCP or Azure architecture. GCP and Azure are disabled in
production until the pipeline rollout, so in practice only local and development data has legacy
GCP or Azure baselines. The spec is updated to match.

## R4 - Which identifiers to match icons on

**Finding.** Each selection the diagram draws has `service_code` and `product_family`:

| Provider | `service_code` | `product_family` |
|---|---|---|
| AWS | service code, e.g. `AmazonEC2` | AWS product family |
| GCP | `service_id`, e.g. `6F81-5844-456A` (Compute Engine) | taxonomy path, e.g. `GCP > Compute > GCE > Persistent Disk > …` |
| Azure | `service_id` | `product_name`, e.g. `Standard SSD Managed Disks` |

The local data has 1,748 GCP services, almost all of them marketplace software, and 188 Azure
services in 29 service families.

**Decision.** Key the GCP and Azure maps on `service_id`, which is stable and the same thing the
catalog filters on. The more specific icons inside a service (FR-008a) are an ordered,
checked-in list per service: a taxonomy prefix for GCP, a product-name pattern for Azure. The
first match wins. This mirrors AWS's `AWS_SERVICE_ICON_BY_CODE_AND_FAMILY`, but GCP's taxonomy is
a path and Azure's product names are free text, so prefix and pattern matching replace AWS's
exact family match.

## R5 - How the icon maps are produced

**Finding.** AWS icons come from `backend/scripts/generate_aws_service_icon_map.py`. It matches
service codes to icon file names (with `difflib`), applies checked-in overrides, writes
`awsServiceIcons.generated.ts` and copies only the used SVGs into
`frontend/src/assets/aws-icons/`. It also writes a backend JSON copy for the Admin tab's AWS
icon-coverage issues, and prints a review report.

**Decision.** Add one new script, `backend/scripts/generate_provider_service_icon_map.py
--provider gcp|azure`, following the same pattern. It writes:

- `frontend/src/lib/{gcp,azure}ServiceIcons.generated.ts`
- `frontend/src/assets/{gcp,azure}-icons/*.svg` (only icons in use)
- a review report: matched, overridden, fallback, plus every service in the compute, storage,
  database or networking categories that has no icon (must be empty, SC-003)

The AWS script, its outputs and its tests are untouched (FR-012).

- **Matching:** exact match on a normalized name (lower case, punctuation and the words
  "Cloud"/"Azure" dropped where the icon set drops them), plus a checked-in `OVERRIDES` table per
  provider. No fuzzy matching: with 1,748 GCP services, fuzzy matching would put first-party
  icons on marketplace products (for example "MySQL by …" → Cloud SQL). Anything not matched
  falls back, as the spec expects.
- **Repeatable:** re-running against the same icon packages and snapshot gives identical output
  (FR-010), as for AWS.
- **Choosing between duplicates:** where Azure has several icons with one name (for example two
  "Workspaces"), the override names the file, and the automatic match takes the lowest-numbered
  file. Either way the choice is stable.

**Alternatives considered.**

- Matching at run time in the browser (rejected: it can't be reviewed, and FR-010 asks for one
  stable choice).
- Extending the AWS script (rejected: AWS's matching rules and outputs would change, and FR-012
  says AWS stays exactly as it is).
- Icon coverage issues in the Admin tab for GCP and Azure (not done): with most GCP services
  falling back by design, the list would be mostly noise. The generator's report covers the
  review instead.

## R6 - Icon packages and licences

**Finding.**

- **GCP:** `images-web/gcp_architecture_icons/svg/` has 216 flat SVGs, named like
  `Compute-Engine.svg`, `Persistent-Disk.svg`, `Cloud-Load-Balancing.svg`,
  `Cloud-External-IP-Addresses.svg`, `Cloud-NAT.svg`, `Cloud-SQL.svg` and `Cloud-Storage.svg`.
  Google publishes these icons for use in architecture diagrams.
- **Azure:** `images-web/azure_architecture_icons/Azure_Public_Service_Icons/Icons/<category>/`
  has about 700 SVGs, named like `NNNNN-icon-service-<Name>.svg`, plus Microsoft's terms of use
  and FAQ. Microsoft's terms allow use in architecture diagrams, and ask that the icons aren't
  modified or used in ways that imply endorsement.

**Decision.** Ship the SVGs unmodified, and only those the maps reference (FR-014). Keep a short
`README.md` in each assets folder naming the package and its terms, as for AWS.

## R7 - The fallback tile

**Finding.** The diagram draws each service as a 60 × 60 px button with an icon and no label.
The name is only in the hover tooltip and accessible name (`servicePopup.ts`).
`SKUSelectionOut` has no service name. The catalog's `CatalogItem` does (`service_name`), and the
selection endpoint already resolves `attributes` and `product_family` from the same lookup
(`architecture_service.py`).

The app already ships both logos for the provider buttons
(`frontend/src/assets/providers/gcp_icon.png`, `azure_icon.png`). The GCP logo is a PNG with a
white background and no transparency. The Azure one is transparent.

**Decision.**

- Add `service_name: str | None` to `SKUSelectionOut`, resolved at response time like
  `product_family` (additive, never stored).
- The fallback tile is the same 60 × 60 px button as an icon:
  - a 14 px provider logo on a 16 px white rounded badge, so the GCP logo's white background
    looks intended in both themes
  - below it, the service name in the theme's text colour, 10 px on 12 px lines, at most three
    lines, cut with an ellipsis. (First built with a 20 px logo and 11 px text: the end-to-end
    screenshots showed the third line cut in half, as only 30 px were left for the name.)
  - the tooltip and accessible name start with the full name, then the usual lines (service
    code, SKU), so hovering shows the whole name. (First built unchanged, which showed only the
    service code: found by the end-to-end test of FR-009.)
- Name source, in order: the service name, then the product family, then the service code. (The
  selection response has no summary.)
- Reuse the existing logo files rather than adding new ones.

**Alternatives considered.**

- Making the GCP logo transparent (rejected: it would mean editing a brand asset).
- Google's `Cloud-Generic.svg` (rejected: the user asked for the provider's logo).
