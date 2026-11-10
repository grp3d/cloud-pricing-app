# Feature Specification: Provider Icons and Price Change Fixes

**Feature Branch**: `020-provider-icons-connector-fixes`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "addressing issues from prior release (i) need to incorporate azure and gcp icons into their respective architectures (at the moment, all gcp and azure icons are defaulting to aws. If icon is not available for a given azure or gcp component, the icon should default to the azure or gcp icon respectively. Icons for azure can be found in images-web/azure_architecture_icons and images-web/gcp_architecture_icons (ii) how can the new connectors be added to the canvas? either the existing connect button needs to work for individual components and/or connector icons need to be available on the canvas ... any other ideas? (iii) there's an issue with the price change calculation for gcp - for example, if I edit the hours per day on sku 6F81-5844-456A, the price change shows up, however if I edit the memory or vcpu count, the total price will change, but the Price Change calculation does not (it'll show the previous price change)"

## Clarifications

### Session 2026-11-06

- Q: Should the connector updates (issue ii) be part of this release? → A: No. They move to the
  [Deferred](#deferred-connector-updates-after-the-ui-overhaul) section, to be picked up after the
  planned UI overhaul, which is expected to redesign how the diagram is drawn on. This release
  covers the Price Change fix and the GCP and Azure icons only.
- Q: When a GCP or Azure service has more specific icons for some of its prices (for example,
  disks inside Compute Engine), should the diagram use them? → A: Yes, for a reviewed list of the
  main cases, as AWS does today. Every other price shows its service's icon (FR-008a).
- Q: What should a GCP or Azure service with no icon of its own show on the diagram? → A: A
  small provider logo with the service's name under it, cut to fit the tile, with the full name
  on hover. Same tile size as an icon. AWS's fallback is unchanged (FR-009).
- Q: After this update, if a stored last calculation lacks vCPU, memory or OS and the Duration
  also changed, what should Price Change show for that calculation? → A: No value, with the note
  "Not available: previous calculation from prior version is unreliable". The next calculation is
  exact (FR-005).
- The decisions below were made for the deferred connector work and are kept with it:
  - Q: What can a connector join? → A: Any two of: a box or an individual service, in any
    combination. The main goal is a clearer diagram. Any connector can carry a data transfer
    selection (option 4).
  - Q: Does the app choose the data transfer price from the connector's ends? → A: No. The user
    chooses it. The app lists the prices that fit the connector's ends first, and warns without
    blocking when a choice clearly doesn't fit. Graduated tiers are applied to the quantity
    automatically, as today. Choosing the price automatically is left for a possible later
    feature.
  - Q: Should an AWS connector's service search start at data transfer prices, as GCP and Azure
    connectors do? → A: Yes. The user can still change the filter or search everything.
  - Q: Do branching connectors (one-to-many, many-to-one) come back? → A: No. They stay deferred.
  - Service-connector rules (suggested defaults, accepted with the answers above): a service end
    is in its box's region; a service can't be connected to itself or to the box it sits in;
    deleting a service removes its connectors, asking first if one carries data transfer; moving
    a service to another box keeps its connectors.

## Context

This feature fixes two problems found after release v0.0.2 (feature 019):

1. **Price Change ignores some GCP and Azure edits.** Price Change compares the architecture's
   current contents with the last calculation. That comparison looks only at the service, SKU,
   price type, purchase option and quantity. It doesn't look at a GCP machine's vCPU count or
   memory, or at an Azure VM's operating system. So after editing only those, the total changes
   but Price Change keeps showing the previous value. Editing hours per day works, because that
   changes the quantity.
2. **Wrong icons on GCP and Azure diagrams.** Every service on a GCP or Azure architecture's
   diagram is drawn with an AWS icon, usually the generic AWS one, because the diagram only
   knows how to find AWS icons.

A third issue, making connectors easier to add and letting them join individual services, is
deferred until after the UI overhaul. See
[Deferred: Connector Updates](#deferred-connector-updates-after-the-ui-overhaul).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Price Change reflects every pricing edit (Priority: P1)

A user prices a GCP architecture, then changes a machine's vCPU count or memory and calculates
again. Price Change shows the difference between the new total and the previous one, just as it
does after changing hours per day. The same applies to an Azure VM's operating system and to any
other setting that changes a price.

**Why this priority**: Price Change is a number users rely on to compare options, and today it
is silently wrong for GCP and Azure. A wrong figure is worse than a missing one.

**Independent Test**: On a GCP architecture with one Compute Engine machine, calculate, change
only the vCPU count, calculate again. Price Change equals the new total minus the previous total.
Repeat with memory, and with an Azure VM's operating system.

**Acceptance Scenarios**:

1. **Given** a calculated GCP architecture, **When** the user changes only a machine's vCPU count
   and calculates, **Then** Price Change equals the new total minus the previous total.
2. **Given** a calculated GCP architecture, **When** the user changes only a machine's memory and
   calculates, **Then** Price Change equals the new total minus the previous total.
3. **Given** a calculated Azure architecture, **When** the user switches a VM between Linux and
   Windows and calculates, **Then** Price Change equals the new total minus the previous total.
4. **Given** a calculated GCP architecture, **When** the user changes a machine's vCPU count
   **and** switches the Duration (monthly or yearly) before calculating, **Then** Price Change
   compares against the previous contents priced at the new Duration, including the previous
   vCPU count and memory.
5. **Given** a calculated architecture, **When** the user changes only a machine's vCPU count or
   memory, or a VM's operating system, **Then** the "updated since last pricing" notice appears
   until the user calculates again.
6. **Given** a calculated architecture, **When** the user calculates again with nothing changed,
   **Then** Price Change stays as it was (today's behaviour, unchanged).
7. **Given** a GCP or Azure architecture last calculated before this update, **When** the user
   switches the Duration and calculates, **Then** Price Change shows no value, with the note
   "Not available: previous calculation from prior version is unreliable", and the following
   calculation shows a correct Price Change.

---

### User Story 2 - GCP and Azure diagrams show their own icons (Priority: P2)

A user building a GCP or Azure architecture sees each service drawn with that provider's official
icon (for example, Compute Engine's icon on GCP, Virtual Machines' icon on Azure). A service with
no matching icon is drawn as a tile with a small provider logo and the service's name, never
with an AWS icon.

**Why this priority**: The diagram is the part of the app people share and present. AWS icons on
a GCP or Azure diagram make it look wrong and confuse anyone reading it.

**Independent Test**: Add a Compute Engine machine and a Cloud Storage bucket to a GCP
architecture, and a Virtual Machine and a Storage account to an Azure architecture. Each shows
its own service icon. Add a service with no icon of its own: it shows the GCP or Azure logo with
the service's name. No AWS icon appears on either diagram.

**Acceptance Scenarios**:

1. **Given** a GCP architecture, **When** the user adds a service that has a GCP icon, **Then** the
   diagram shows that service's GCP icon.
2. **Given** an Azure architecture, **When** the user adds a service that has an Azure icon,
   **Then** the diagram shows that service's Azure icon.
3. **Given** a GCP or Azure architecture, **When** the user adds a service with no matching icon,
   **Then** the diagram shows the GCP or Azure logo respectively, with the service's name under
   it, and the full name on hover.
4. **Given** an AWS architecture, **When** the user views it, **Then** its icons are exactly as
   they are today.
5. **Given** a GCP or Azure architecture saved before this feature, **When** the user opens it,
   **Then** its services show the correct provider icons with no action from the user, and its
   icon positions are unchanged.
6. **Given** any provider's diagram, **When** the user switches between light and dark theme,
   **Then** every icon, including the logos and names on fallback tiles, stays clearly visible.

---

### Edge Cases

- **A GCP service sold through the marketplace** (most of the roughly 1,750 GCP services are
  third-party images and software): shows the GCP fallback tile with its name, unless it clearly
  matches a first-party GCP service icon.
- **A very long service name** (for example, "OpenLogic CentOS 7.8 (v20200922) - Security
  Hardened"): cut to fit with an ellipsis. The full name shows on hover.
- **Several services on one diagram fall back**: each tile shows its own name, so they can be
  told apart without hovering.
- **A Compute Engine disk price or an Azure managed disk price**: shows the disk icon from its
  provider's set, not the Compute Engine or Virtual Machines icon.
- **Several icons could match one service** (for example, Azure has more than one "Workspaces"
  icon): one icon is chosen consistently, so the same service always shows the same icon.
- **A service's icon changes after this feature** (from an AWS icon to its own): the icon's
  position and size on the diagram are kept.
- **A GCP machine's vCPU count or memory is edited and then put back** to the value it had at the
  last calculation: this counts as unchanged, as it does today for quantity.
- **An architecture last calculated before this feature**: its stored last calculation doesn't
  record vCPU, memory or operating system. At the next calculation:
  - Duration unchanged: Price Change is the new total minus the previous total, which is correct
    whatever changed.
  - Duration changed, on a GCP or Azure architecture: Price Change shows no value, with the note
    "Not available: previous calculation from prior version is unreliable". (Its stored
    calculation has no regions either, and GCP and Azure have no default region to fall back to.)
  - Duration changed, on an AWS architecture: handled exactly as today.
  Either way, a complete last calculation is then stored, so the following comparison is exact.
  It never shows an error.
- **A connector's data transfer service on a GCP or Azure architecture**: drawn with that
  provider's icon or its fallback tile, the same as any other service.

## Requirements *(mandatory)*

### Functional Requirements

**Price Change (User Story 1)**

- **FR-001**: Price Change MUST treat any edit that can change a service's price as a change to
  the architecture. This includes the service, SKU, price type, purchase option, quantity, the
  region it is priced in, a GCP machine's vCPU count and memory, an Azure VM's operating system,
  and any other provider-specific pricing setting a service has.
- **FR-002**: When the contents changed and the Duration did not, Price Change MUST equal the new
  total minus the previous total.
- **FR-003**: When the Duration changed (with or without other changes), the previous contents
  MUST be priced at the new Duration with all their settings, including their provider, region,
  vCPU count, memory and operating system, before Price Change is worked out.
- **FR-004**: The "updated since last pricing" notice MUST appear after any edit covered by
  FR-001, and only until the next calculation.
- **FR-005**: A last calculation stored before this feature MUST still be usable, without an
  error, and MUST be replaced by a complete one at the next calculation. If the Duration changed
  and the architecture is a GCP or Azure one (whose stored calculation lacks the settings and
  regions FR-003 needs), Price Change MUST show no value for that calculation, with the note "Not available: previous calculation from prior
  version is unreliable", rather than a figure that could be wrong. When the Duration is
  unchanged, the direct difference (FR-002) MUST still be shown.

**Icons (User Story 2)**

- **FR-006**: The diagram MUST choose a service's icon from the architecture's own provider:
  AWS icons for AWS, GCP icons for GCP, Azure icons for Azure.
- **FR-007**: GCP icons MUST come from the official GCP architecture icon set provided
  (`images-web/gcp_architecture_icons`), and Azure icons from the official Azure icon set provided
  (`images-web/azure_architecture_icons`).
- **FR-008**: Every GCP and Azure service that has a clearly matching icon in its provider's set
  MUST show that icon. At minimum this MUST cover the services the app's search groups under
  compute, storage, database and networking.
- **FR-008a**: Inside large GCP and Azure services, a reviewed list of the main kinds of price
  (such as disks, IP addresses, snapshots and load balancing) MUST show their own more specific
  icon where the provider's set has one, as AWS does for some services today. Every other price
  shows its service's icon. Prices not on the list are never guessed.
- **FR-009**: A GCP or Azure service with no matching icon MUST show a fallback tile: a small logo
  of its provider (Google Cloud or Azure) with the service's name under it. The name MUST be cut
  to fit the tile (at most three lines), and the full name MUST still show on hover, as for every
  service today. The tile MUST be the same size as an icon. It MUST never show an AWS icon.
- **FR-009a**: AWS's fallback (the generic AWS icon, no name) MUST stay as it is.
- **FR-010**: The same service MUST always resolve to the same icon.
- **FR-011**: Icons MUST stay clearly visible in both light and dark theme.
- **FR-012**: AWS icons and their behaviour MUST stay exactly as they are.
- **FR-013**: Changing which icon a service shows MUST NOT move, resize or reorder anything on an
  existing diagram.
- **FR-014**: Only icons the provider's terms allow to be used in architecture diagrams MUST be
  shipped, and only the ones the app actually uses.

### Key Entities *(include if feature involves data)*

- **Service icon**: The picture drawn for one service on the diagram. It is chosen from the
  architecture's provider's icon set: first a more specific icon for that kind of price, if it is
  on the reviewed list, then the service's own icon. For GCP and Azure, the fallback is a tile
  with the provider's logo and the service's name; for AWS it is the generic AWS icon.
  It is a display choice only and isn't stored with the architecture.
- **Last calculation (Price Change baseline)**: The total, Duration and full pricing settings of
  every service at the last calculation, now including provider-specific settings such as vCPU
  count, memory and operating system. Kept per architecture in the user's browser, as today.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every pricing setting a user can edit on an AWS, GCP or Azure service, editing
  it alone and calculating again gives a Price Change equal to the new total minus the previous
  total, in 100% of tested cases.
- **SC-002**: On GCP and Azure diagrams, 0 services show an AWS icon, and every fallback tile
  shows a readable name (at least the first word or two) without hovering.
- **SC-003**: Every service the app's search groups under compute, storage, database or
  networking for GCP and Azure shows its own provider's service icon, not the fallback tile.
- **SC-004**: Opening a GCP or Azure architecture saved before this feature shows the new icons
  with 0 changes to the layout.

## Assumptions

- The two icon folders named in the request are the official, unmodified icon packages from Google
  and Microsoft. Their terms allow use in architecture diagrams, as the AWS package's do.
- "Defaults to the azure or gcp icon" means the provider's logo, shown small on a tile with the
  service's name (see Clarifications). The logos already in `images-web/gcp_icon.png` and
  `images-web/azure_icon.png`, or equivalent logos from each provider's official package, are
  used.
- Icons are matched to services ahead of time and reviewed, as was done for AWS, not guessed
  while the app runs.
- Most GCP services are marketplace software with no icon of their own, so most of them showing
  the GCP fallback tile is expected.
- The Price Change fix covers every provider. For AWS, results change in one case only: after a
  Duration switch on an architecture with boxes outside us-east-1, the previous contents are now
  priced in their own regions, where v0.0.2 priced them at us-east-1 rates. The new figure is the
  correct one. Moving a service to a box in another region now also counts as a change.
- The Price Change baseline stays in the browser (as decided in 019). It isn't moved to the
  account in this feature.
- Connectors are unchanged in this release: same ways to add them, same ends (boxes only), same
  arrow styles and same service search.
- The UI overhaul is a separate, later feature. This release makes no layout or styling changes
  beyond showing the right icons.
- This feature builds on v0.0.2 (019) and will ship as v0.0.3.

---

## Deferred: Connector Updates (after the UI overhaul)

**Not part of this release.** Issue (ii) from the request is deferred so the UI overhaul can
design how connectors are drawn and added from the start, instead of fitting them into today's
layout and redoing them afterwards. Everything below was agreed on 2026-11-06 (see
Clarifications) and is kept here so the connector feature can start from it. Requirement and
criterion numbers are prefixed `D-` so they don't collide with this release's.

When this work is picked up, check it against the overhaul's design first. The ways of adding a
connector (D-US1) are the most likely to change. The connector-end rules (D-US2) and the data
transfer behaviour (D-US3) mostly don't depend on the UI.

### Today's behaviour (as of v0.0.2)

A connector can be added in two ways: the "Connect" button above the collections list (pick a
From box and a To box), or by dragging from the edge of one box to another. Both join two boxes
(collections), never two individual services, and a new connector always starts as a plain line.
Its arrow style can only be set afterwards, from the selected connector's details. Nothing on the
diagram itself suggests how to draw one. A connector's service search starts at data transfer for
GCP and Azure (the user can change it). AWS search has no such filter and starts with the whole
catalogue.

### D-US1 - Adding connectors is obvious and quick

A user wants to show how data flows through the architecture. They can see on the diagram itself
how to draw a connector, and choose its style (plain line, one-way or two-way) as they create it.

**Independent Test**: On an architecture with two boxes, a first-time user draws a one-way
connector between them without help, starting from the diagram, in 3 actions or fewer. The arrow
style is right as soon as the connector appears.

**Acceptance Scenarios**:

1. **Given** an architecture with at least two boxes, **When** the user looks at the diagram,
   **Then** there is a visible control on the diagram for adding a connector.
2. **Given** the user starts adding a connector, **When** they choose a style (plain line, one-way
   or two-way) and pick its two ends, **Then** the new connector appears with that style, without
   a separate edit afterwards.
3. **Given** the user hovers over or selects a box, **When** it can be connected, **Then** its
   connection points are visible, so dragging a connector from it is discoverable.
4. **Given** the user opens the "Connect" button's dialog, **When** they create a connector,
   **Then** they can choose its style there too.
5. **Given** a connector created by any of these ways, **When** the user prices the architecture,
   reloads, exports or imports it, **Then** it behaves exactly like a connector created today.

### D-US2 - Connect individual services

A user connects one service to another (for example, a web server in one box to a database in
another), or a service to a box, so the diagram shows exactly which parts talk to each other.
Any connector, whatever its ends, can carry a data transfer price.

**Independent Test**: In an architecture with two boxes, each holding one service, connect the
two services with a one-way connector. The line runs between the two service icons. Add a data
transfer price to it, calculate: the price is in the total, priced in the "from" service's box
region. Reload, export and import: the connector still joins the same two services.

**Acceptance Scenarios**:

1. **Given** two services in different boxes, **When** the user connects them, **Then** the
   connector is drawn between the two service icons.
2. **Given** a service and a box, **When** the user connects them, **Then** the connector is drawn
   between the service icon and the box.
3. **Given** a connector with a service at one or both ends, **When** the user adds a data transfer
   price and calculates, **Then** it is priced in the region of the "from" end's box, as for a
   box-to-box connector.
4. **Given** a service that ends one or more connectors, **When** the user deletes the service,
   **Then** those connectors are removed too, and if any of them carries a data transfer price the
   user is asked to confirm first.
5. **Given** a service that ends a connector, **When** the user moves the service into another
   box, **Then** the connector stays attached to the service. If the new box is in another region,
   the connector's data transfer is priced in that region from then on, and the "updated since
   last pricing" notice appears.
6. **Given** a service, **When** the user tries to connect it to itself or to the box it sits in,
   **Then** the app doesn't allow it.

### D-US3 - Choosing the right data transfer price

A user adding data transfer to a connector sees the data transfer prices first, with the ones
that fit the connector's ends (for example, the prices between its two regions) at the top. If
they pick a price that clearly doesn't fit, the app warns them but lets them keep it. Choosing the
price stays the user's decision.

**Independent Test**: On an AWS architecture with boxes in two regions, open a connector's
service search: it starts at data transfer prices, with the prices between those two regions at
the top. Pick a price for two other regions: a warning appears, and the price can still be kept
and is priced as chosen.

**Acceptance Scenarios**:

1. **Given** a connector on an AWS, GCP or Azure architecture, **When** the user opens its service
   search, **Then** it starts at data transfer prices, and the user can change the filter or search
   everything.
2. **Given** a connector whose ends are in different regions, **When** the user searches for data
   transfer, **Then** prices for that pair of regions are listed first, where the price data says
   which regions a price covers.
3. **Given** a connector whose ends are in the same region, **When** the user searches for data
   transfer, **Then** prices for transfer within a region are listed first, where the price data
   says so.
4. **Given** a connector, **When** the user picks a data transfer price that clearly doesn't fit
   its ends (for example, one for another pair of regions), **Then** a warning explains why, the
   choice is kept, and it is priced as chosen.
5. **Given** a connector with a data transfer price, **When** its ends change region (by moving a
   service or changing a connector end), **Then** the warning is shown or cleared to match.
6. **Given** a data transfer price whose data doesn't say which path it covers, **When** the user
   picks it, **Then** no warning is shown.

### Deferred edge cases

- **Adding a connector between two things that are already connected**: refused with a clear
  message, as today. A connector from box A to box B and one from a service in A to box B are
  different connectors, and both are allowed.
- **Adding a connector from a box to itself**: not allowed, as today.
- **A service connected to the box it sits in, or to another service in the same box**: the first
  is not allowed. The second is allowed; its ends are in the same region.
- **A service connected to box B is moved into box B** (so the connector would join a service to
  the box it sits in): the connector is removed, asking first if it carries data transfer.
- **A box is deleted while connectors end at services inside it**: those services are deleted
  with the box, as today, and their connectors are removed with them, asking first if any carries
  data transfer.
- **Two or more connectors meet at one small service icon**: each stays visible and can be
  selected on its own.
- **A connector's two ends are in regions from different parts of the world** (for example, a
  US region and an Asian one): handled like any other pair of regions.
- **An internet-egress price on a connector between two boxes in the same region** (often used to
  stand for users outside the cloud): allowed with no warning, because the app can't tell which
  box stands for the internet.
- **A cross-zone price on a same-region connector**: no warning, because the app doesn't know
  zones.
- **An architecture exported with service connectors, imported into a version that only knows
  box connectors**: not supported. Older versions aren't changed.
- **The user cancels while adding a connector** (for example, presses Escape or clicks empty
  canvas): nothing is created.
- **The diagram's pop-out view**: offers the same ways to add a connector as the main diagram.
- **A viewer with read-only access to a shared architecture**: sees no controls for adding
  connectors.

### Deferred requirements

**Adding connectors (D-US1)**

- **D-FR-001**: The diagram MUST offer a visible control for adding a connector, available in both
  the main diagram and its pop-out view.
- **D-FR-002**: When adding a connector, the user MUST be able to choose its style (plain line,
  one-way or two-way) before or as it is created.
- **D-FR-003**: The "Connect" button's dialog MUST also let the user choose the style.
- **D-FR-004**: A box's connection points MUST be visible when the user hovers over or selects it,
  so that dragging a connector between boxes is discoverable.
- **D-FR-005**: Users who can only view an architecture MUST NOT see controls for adding
  connectors.

**Connector ends (D-US2)**

- **D-FR-006**: Each end of a connector MUST be either a box or an individual service, in any
  combination: box to box (as today), service to service, or service to box.
- **D-FR-007**: A connector created in any of these ways MUST be saved, priced, exported, imported
  and copied exactly like one created today, and its style MUST never change a price.
- **D-FR-008**: The existing rules MUST still apply: no connector from something to itself, no
  duplicate connector between the same two ends, both ends in the same architecture. In addition,
  a service MUST NOT be connected to the box it sits in.
- **D-FR-009**: A service end MUST count as being in the region of the box it sits in. A
  connector's data transfer MUST be priced in the region of its "from" end, as today.
- **D-FR-010**: The diagram MUST draw a connector that ends at a service to that service's icon,
  and keep it attached when the icon or its box is moved or resized, or when the pop-out view is
  used.
- **D-FR-011**: Deleting a service MUST remove every connector that ends at it. If any of those
  connectors carries a data transfer price, the user MUST confirm first. Deleting a box MUST do
  the same for connectors that end at the box or at any service inside it.
- **D-FR-012**: Moving a service into another box MUST keep its connectors attached to it, except
  a connector to that same box, which is removed (D-FR-008), asking first if it carries data
  transfer. If the service's region changes, its connectors' data transfer MUST be priced in the
  new region, and the "updated since last pricing" notice MUST appear.
- **D-FR-013**: Branching connectors (one-to-many and many-to-one) stay deferred, as decided for
  v0.0.2.

**Data transfer on connectors (D-US3)**

- **D-FR-014**: Any connector, whatever its ends, MUST be able to carry a data transfer price. The
  user chooses which price. The app MUST NOT replace or change it.
- **D-FR-015**: A connector's service search MUST start at data transfer prices for all three
  providers. For AWS this means gathering the data transfer prices AWS lists under its own data
  transfer service and under other services (for example, those that list their own transfer
  out). The user MUST be able to change the filter or search everything.
- **D-FR-016**: When searching data transfer prices for a connector, the prices that fit its ends
  MUST be listed first: those between its two regions when they differ, and those within a region
  when they match. This applies only where the price data says which regions a price covers.
- **D-FR-017**: When a connector's data transfer price clearly doesn't fit its ends (a price for
  another region or pair of regions, or a cross-region price on a same-region connector), the app
  MUST show a warning saying why. It MUST NOT block the choice or change the price.
- **D-FR-018**: The warning MUST be updated whenever the connector's ends change region, and MUST
  NOT be shown when the price data doesn't say which path a price covers.
- **D-FR-019**: Graduated tiers MUST keep being applied to a connector's data transfer quantity
  automatically, as they are today.

### Deferred key entities

- **Connector**: A link between two ends on one architecture's diagram, with an arrow style and
  an optional data transfer price. Each end is a box or a service. Its "from" end's box sets the
  region its data transfer is priced in.
- **Connector end**: One end of a connector: a box, or a service inside a box. A service end takes
  its region from its box.
- **Data transfer fit**: Whether a data transfer price suits a connector's ends (fits, doesn't fit
  or unknown), worked out from the regions the price covers. It is shown as a warning only, and is
  never stored or used to change a price.

### Deferred success criteria

- **D-SC-001**: A first-time user can add a one-way connector between two boxes, starting from the
  diagram, in 3 actions or fewer, and 4 out of 5 test users do so without help.
- **D-SC-002**: Connectors added in the new ways survive reload, export and import with their
  style and ends intact 100% of the time. Their style never changes an architecture's total.
- **D-SC-003**: A user can connect two services in different boxes in 3 actions or fewer.
- **D-SC-004**: On an AWS connector between boxes in two different regions, a data transfer price
  for that pair of regions appears among the first 5 search results, without the user typing a
  search.
- **D-SC-005**: For every AWS data transfer price whose data names its regions, a price for a
  different pair of regions than the connector's shows the warning, and a matching one doesn't,
  in 100% of tested cases.
- **D-SC-006**: A connector's data transfer price is priced in the "from" end's region the same
  way whether that end is a box or a service in it, with 0 difference in the total.

### Deferred assumptions

- Arrow styles stay as they are: plain line, one-way (reversible) and two-way. Existing connectors
  and their styles are unchanged.
- No new pricing logic is added for connectors. A connector's optional data transfer selection is
  priced as today, and still holds at most one price.
- The app doesn't choose data transfer prices from a connector's ends. It doesn't know zones or
  which box stands for the internet, so the user knows the path better. Choosing automatically
  could be a later feature.
- AWS data transfer prices name the regions they cover, so suggestions and warnings work best for
  AWS. How much GCP's and Azure's price data says about the path is to be checked when this work
  is planned. Where it says nothing, there are no suggestions or warnings for that provider, and
  searching still works.
- The new search filter for AWS connectors is a starting point only. AWS search for boxes keeps
  working as today, with no new filter.
- Existing box-to-box connectors stay exactly as they are.
