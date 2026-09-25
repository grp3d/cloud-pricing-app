# UI Contract: 015-canvas-service-icons

This describes observable UI behavior that component tests and manual QA can check against.
Data shapes are in [data-model.md](../data-model.md).

## A. Canvas service icon (column 4 and pop-out canvas)

Replaces each `<li><button>{service_code} / {sku} — {detail}</button></li>` row in
`ServiceList` (`ArchitectureDiagramPanel.tsx`).

| Aspect | Contract |
|---|---|
| Element | One `<button type="button">` per SKU selection, containing an `<img alt="">` for the resolved icon (two imgs, one hidden per theme, for theme-aware icons). |
| Layout | Buttons in a `flex flex-wrap` row inside the box, in the same order as today's list. The box's measured height grows to fit the wrapped rows. |
| Size | 24 × 24 CSS px at raw React Flow zoom 1. It scales with the viewport transform like all other node content. |
| Accessible name | `aria-label` = `buildServicePopupLines(selection).join(", ")` |
| Selected state | When `selectedServiceId === selection.id`: a visible ring or outline (replaces today's underline) and `aria-pressed="true"`. |
| Click / Enter / Space | `onSelectService(selection.id)` with `stopPropagation()`, same as today. |
| Empty box | "No services yet." text unchanged. `hideEmptyMessage` behavior unchanged. |
| Unchanged | Box/VPC name labels, connector edges and labels, resize handles, and drag behavior. |

## B. Service pop-up

| Aspect | Contract |
|---|---|
| Trigger | Pointer hover **or** keyboard focus on the icon button. It closes on pointer leave, blur or Escape. |
| Component | The existing shadcn `Tooltip` / `TooltipContent` (portal). |
| Content | One block element per line from `buildServicePopupLines`, in order, with no empty lines. |
| Scaling | Content font size = `text-2xs × current canvas zoom`, with spacing in `em`, so the pop-up grows and shrinks with the zoom controls. |
| Example | For DynamoDB `3ERQSZWPAMX2JWHN`: `AmazonDynamoDB` / `Sku: 3ERQSZWPAMX2JWHN` / `DynamoDB PayPerRequest Read Request Units` / `UsageType: EU-ReadRequestUnits` / `Operation: PayPerRequestThroughput` |

## C. Pricing column (column 5)

Ordered content of the result section, top to bottom:

1. Duration select + Calculate button (unchanged). On switching architecture, the select shows
   the stored result's duration when one exists.
2. `Total: …` + Price Change indicator (the active architecture's own values).
3. Warnings / unpriceable notices (the active architecture's own).
4. **Price per Sku** section. The heading row is `[Price per Sku ……… (wrap toggle)]`: heading
   text left (truncates if narrow) and the word-wrap toggle button right-aligned, flush with the
   price values' right edge. The toggle keeps the same `aria-label`, `aria-pressed`, tooltip text
   and behavior.
5. `Data Timestamp: <snapshot_date>`
6. **Out-of-date notice** (only when the active architecture's priced contents differ from those
   stored with its result): the text `Architecture has been updated since last pricing`, styled
   like other advisory text (amber warning tone, `text-2xs`), with `role="status"`.

The word-wrap toggle no longer renders below the Data Timestamp line.

| State | What column 5 shows |
|---|---|
| Active architecture has no services | Duration + Calculate only (current empty state). No auto-calculation. |
| No stored result, has services | Automatic calculation starts; the existing in-progress state (Calculate disabled) shows, then the result. |
| Stored result | Rendered immediately with no network request. The notice shows if contents diverged. |
| Error for active architecture | The existing `ErrorMessage` with Retry. It is not shown after switching to another architecture, and reappears on switching back (in-memory for this page load). |
