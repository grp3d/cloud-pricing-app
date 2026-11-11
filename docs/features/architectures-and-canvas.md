# Architectures and canvas

An **architecture** belongs to one provider (AWS, GCP or Azure) and one owner. It is made of
collections, the services inside them, and connectors between collections. It's edited in the
Architecture Editor (the left sidebar) and drawn on the canvas.

## Collections and regions

- There are two kinds of collection: **VPC** and **Application** (an application component).
  An Application can sit at the top level or nest inside a VPC.
- Every collection has a region, chosen when it's created. A new Application inside a selected
  VPC takes that VPC's region. The region **locks** once the collection has content.
- An Application can only nest inside a VPC in the same region.
- The service search is scoped to the selected collection's region (and includes SKUs priced
  only globally).
- A new top-level collection is placed inside the visible part of the canvas.

## Services

A service is one SKU with its pricing settings (see [pricing](pricing.md)), added to a
collection or to a connector:

- Search in the Architecture Editor, then either choose a result to open it in the **Service**
  tab and set it up, or use its arrow to add it straight away with default values.
- On the canvas each service is its provider's icon (AWS, GCP or Azure icon set; a labelled
  provider tile where no icon matches). Icons are spaced out inside their box and can be dragged
  to arrange it.
- Hovering or focusing an icon shows the SKU's identifying details. An AWS service starts with
  its service code and SKU; a GCP or Azure service starts with its readable name and
  description, with the codes muted beneath. Then come the region pair (for data transfer), a
  summary of the SKU's attributes and its usage type. The pop-up keeps its normal text size at
  any zoom.
- Selecting an icon opens the service in the **Service** tab.

## Connectors

- A connector links two collections and can carry one data-transfer service, or none.
- Its service search follows the "from" collection's region.
- Arrow style: **None** (the default), **One-way** or **Two-way**. A directional connector can be
  reversed. Arrow styles don't change any price and are kept by export, import and copies.
- Two collections can have several connectors between them.
- On the canvas a connector routes around boxes. Drag its handle to bend it; double-click to go
  back to automatic routing.

## The canvas

- Boxes show their full content: names wrap instead of clipping, and a VPC's region (and an
  Application's, when it isn't inside a VPC) is shown in the box's corner.
- Boxes can be moved and resized; the canvas can be zoomed and its height resized. **Redraw**
  lays the diagram out again.
- The **pop-out** button opens the canvas in an enlarged view.
- Box positions and sizes, icon arrangement, connector bends and sides, and zoom are kept in the
  browser, per architecture (see [workspace and preferences](workspace-and-preferences.md#settings-saved-to-your-account)).

## Not built yet

- **Branching connectors** (one-to-many, many-to-one): specified in 019 and deferred. The API
  accepts the two styles, but the editor offers only None, One-way and Two-way, and nothing draws
  branches.
- **Readable GCP and Azure names on the canvas boxes**: 021 added readable names to the hover
  text, the Service tab and the price list; showing them on the canvas itself is a planned
  follow-up.

## Specs

[001](../../specs/001-assemble-price-aws-architecture/spec.md),
[002](../../specs/002-vpc-component-nesting/spec.md),
[003](../../specs/003-service-selection-improvements/spec.md),
[004](../../specs/004-canvas-pricing-improvements/spec.md),
[005](../../specs/005-resizable-canvas-boxes/spec.md),
[009](../../specs/009-ui-fixes-next-iteration/spec.md),
[010](../../specs/010-multi-region-support/spec.md),
[011](../../specs/011-canvas-connector-popout/spec.md),
[015](../../specs/015-canvas-service-icons/spec.md),
[016](../../specs/016-canvas-icon-layout/spec.md),
[019](../../specs/019-gcp-azure-providers-trends/spec.md) (US5),
[020](../../specs/020-provider-icons-connector-fixes/spec.md) (US2),
[021](../../specs/021-workspace-layout-redesign/spec.md) (US5, US7, US9).
