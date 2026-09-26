# UI Contract: 016-canvas-icon-layout

Observable behavior for component tests and manual QA. The geometry is defined in
[data-model.md](../data-model.md) §5–6.

## A. Canvas icons (column 4 and the pop-out canvas)

| Aspect | Contract |
|---|---|
| Size | Each icon button is 60 × 60 canvas units. It scales with zoom as before. |
| Default placement | Up to 3 per row, 90 canvas units apart on both axes, in service order. |
| Box width | Wide enough for its widest row of up to 3 icons, and never narrower than today's defaults (VPC 220, Application 200, nested Application 180). |
| Box height | Grows to contain every icon, plus room for the region label. |
| Hand placement | Saved per browser and restored on reload. Invalid saved positions fall back to the first free default slot. |
| Click | Pointer movement of 4 screen px or less counts as a click: it selects the service (015 behavior). |
| Drag in the same box | The icon follows the pointer. On release it goes to the nearest valid spot (≥ 90 apart from others, inside the box) and is saved. |
| Drag in a VPC, not over a nested box | The icon stays in the VPC's own-services area, which grows and pushes the nested boxes down. |
| Drag into another box, same region | The service moves (PATCH `collection_id`). The icon is shown in the target at the drop point or the nearest valid spot. On failure it returns, and the error shows in column 2. |
| Drag into a box in another region | No request is sent. The icon returns, and column 2 shows `"<service>" can only move to a box in <region>.` |
| Drop on empty canvas | The icon returns. No message. |
| While dragging | The dragged icon is drawn above every box and never hidden. It never pans the canvas or drags the box. |

## B. Hover pop-up

The lines, in order, each omitted when empty:
1. service code
2. `Sku: <sku>`
3. the data-transfer region pair (data transfer only)
4. the summary line, **excluding** any value shown on its own line below
5. `UsageType: <usagetype>`
6. `<key>: <value>` for each of these 15 keys, in this order: databaseEngine, processorArchitecture,
   physicalProcessor, clockSpeed, tenancy, storageType, cacheEngine, networkPerformance, memory,
   storageMedia, volumeType, minVolumeSize, maxVolumeSize, storageClass, deploymentOption

There is **no** `Operation:` line.

## C. Error placement

| Action | Error shows in |
|---|---|
| Create, delete, import or share an architecture | Column 1 only |
| Create or delete a collection; region change; nesting (including cross-region nesting); connectors; moving an icon between boxes | Column 2 only |
| Service configuration (column 3) | Column 3, unchanged |

Dismissing an error clears only that column's error.

## D. New top-level collection placement

A newly created top-level box is placed:
- fully inside the visible canvas when it fits;
- not overlapping any box, when free space exists there;
- otherwise at the visible top-left.

The position is saved like a manual move. Nested boxes are unchanged.

## E. Admin tab

```
┌ User Management ─────────────────────────────┐
│ (today's user table + Create New User)       │
└──────────────────────────────────────────────┘
┌ System Information ──────────────────────────┐
│ Active pricing snapshot: 2026-09-24  [Pinned]│
│ Last checked: 26 Sep 2026, 17:05             │
│ Waiting: 2026-09-27 — no completion marker…  │
│ (last check error, if any, in red)           │
│                                              │
│ Issues                                       │
│ Type          │ Detail            │ Snapshot │ New │
│ Missing icon  │ AmazonHoneycode … │ 09-24    │     │
│ Missing region│ eu-west-2         │ 09-27    │  —  │
└──────────────────────────────────────────────┘
```

- **Refresh**: data is refetched every 60 s while the tab is open.
- **Empty states**: "No issues." when the Issues table has no rows; no Waiting row when nothing is
  waiting.
- **Access**: only admins can see or reach the Admin tab (unchanged).
