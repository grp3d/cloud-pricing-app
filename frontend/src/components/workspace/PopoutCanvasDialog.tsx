import { ReactFlowProvider } from "@xyflow/react";
import { GripHorizontal } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { type Collection, type DataConnector } from "../../api/client";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { ArchitectureDiagramPanel } from "./ArchitectureDiagramPanel";

const DEFAULT_WIDTH_RATIO = 0.9;
const DEFAULT_HEIGHT_RATIO = 0.85;
const MIN_WIDTH = 480;
const MIN_HEIGHT = 360;
// How much of the dialog must stay reachable on-screen while dragging — a floor, not a full
// clamp, so it can still be dragged mostly off-screen if the user wants columns 2/3 fully
// clear, but never loses the drag handle/close button entirely off any edge.
const MIN_VISIBLE_MARGIN = 40;

/** Drag-to-move title bar (live user report: the pop-out could be resized but not repositioned,
 * making it impossible to keep columns 2/3 reachable while it's open — this app never
 * committed to a fixed in-viewport position for it, that was just this dialog's original,
 * too-narrow default). Same proven `onPointerDown`/`setPointerCapture`/`pointermove` pattern as
 * `PopoutResizeHandle` below, dragging position instead of size. */
function PopoutDragHandle({ onDrag }: { onDrag: (deltaX: number, deltaY: number) => void }) {
  const lastRef = useRef({ x: 0, y: 0 });

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label="Move the pop-out canvas"
      className="flex h-6 shrink-0 cursor-move touch-none items-center justify-center rounded-t text-muted-foreground hover:bg-accent active:bg-accent"
      onPointerDown={(e) => {
        e.preventDefault();
        lastRef.current = { x: e.clientX, y: e.clientY };
        const target = e.currentTarget;
        target.setPointerCapture(e.pointerId);

        const handleMove = (moveEvent: PointerEvent) => {
          const deltaX = moveEvent.clientX - lastRef.current.x;
          const deltaY = moveEvent.clientY - lastRef.current.y;
          lastRef.current = { x: moveEvent.clientX, y: moveEvent.clientY };
          onDrag(deltaX, deltaY);
        };
        const handleUp = () => {
          target.removeEventListener("pointermove", handleMove);
          target.removeEventListener("pointerup", handleUp);
        };
        target.addEventListener("pointermove", handleMove);
        target.addEventListener("pointerup", handleUp);
      }}
    >
      <GripHorizontal className="size-4" aria-hidden="true" />
    </div>
  );
}

/** Corner resize grip for the pop-out, extending `ArchitectureDiagramPanel.tsx`'s
 * `DiagramResizeHandle`/`WorkspacePage.tsx`'s `ColumnResizeHandle` pattern to both dimensions
 * at once (research.md §4) — the same proven `onPointerDown`/`setPointerCapture`/`pointermove`
 * approach, not the native CSS `resize` this codebase already found unreliable for exactly this
 * kind of drag handle. */
function PopoutResizeHandle({ onDrag }: { onDrag: (deltaX: number, deltaY: number) => void }) {
  const lastRef = useRef({ x: 0, y: 0 });

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize the pop-out canvas"
      className="absolute right-0 bottom-0 z-10 size-4 cursor-nwse-resize touch-none rounded-br border-border/0 bg-transparent hover:bg-primary/20 active:bg-primary/30"
      onPointerDown={(e) => {
        e.preventDefault();
        lastRef.current = { x: e.clientX, y: e.clientY };
        const target = e.currentTarget;
        target.setPointerCapture(e.pointerId);

        const handleMove = (moveEvent: PointerEvent) => {
          const deltaX = moveEvent.clientX - lastRef.current.x;
          const deltaY = moveEvent.clientY - lastRef.current.y;
          lastRef.current = { x: moveEvent.clientX, y: moveEvent.clientY };
          onDrag(deltaX, deltaY);
        };
        const handleUp = () => {
          target.removeEventListener("pointermove", handleMove);
          target.removeEventListener("pointerup", handleUp);
        };
        target.addEventListener("pointermove", handleMove);
        target.addEventListener("pointerup", handleUp);
      }}
    >
      <svg viewBox="0 0 16 16" className="size-full text-muted-foreground" aria-hidden="true">
        <path
          d="M14 3 L3 14 M14 8 L8 14 M14 13 L13 14"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export interface PopoutCanvasDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  architectureId: string;
  collections: Collection[];
  connectors: DataConnector[];
  onCreateConnector: (from: string, to: string) => void;
  onUpdateCollectionParent: (id: string, parentId: string | null) => void;
  onRejectedNesting: (applicationName: string, vpcName: string) => void;
  onRefresh: () => void;
}

/**
 * 011-canvas-connector-popout, spec FR-007–FR-011, research.md §3/§4: an enlarged, resizable,
 * in-tab view of the same architecture canvas as column 4 — a second, fully independent
 * `ArchitectureDiagramPanel` instance (its own `ReactFlowProvider`, since one provider only
 * ever manages one React Flow instance's internal store; two under the same provider would
 * fight over shared state rather than behave independently) with its own local
 * selection/box-height state, mirroring the shape `WorkspacePage.tsx` owns for column 4 without
 * sharing it. `collections`/`connectors`/the mutation callbacks are the exact same props/
 * functions `WorkspacePage.tsx` already passes to column 4 — both instances read the same
 * TanStack Query cache, so any edit from columns 2/3 (which already invalidates that cache)
 * appears in both automatically (FR-009), with no new sync mechanism.
 *
 * `modal={false}` plus no `DialogOverlay` (`overlay={false}`, `ui/dialog.tsx`) is deliberate,
 * not a default — a default *modal* `Dialog` would trap focus and block pointer events on
 * column 4 underneath, directly contradicting FR-011 (`/speckit-analyze` finding F1). With no
 * overlay, "outside" the pop-out is column 4's own live canvas, so outside-click no longer
 * doubles as a dismiss gesture (`onPointerDownOutside` prevented below) — only the close button
 * and Escape close it (spec.md Edge Cases, updated during implementation to match).
 */
export function PopoutCanvasDialog({
  open,
  onOpenChange,
  architectureId,
  collections,
  connectors,
  onCreateConnector,
  onUpdateCollectionParent,
  onRejectedNesting,
  onRefresh,
}: PopoutCanvasDialogProps) {
  const [size, setSize] = useState(() => ({
    width: Math.round(window.innerWidth * DEFAULT_WIDTH_RATIO),
    height: Math.round(window.innerHeight * DEFAULT_HEIGHT_RATIO),
  }));
  // Explicit pixel position (not `DialogContent`'s default centered-via-transform placement)
  // so it can be dragged — initialized to the same centered spot that default would have
  // produced, so opening the pop-out looks unchanged until the user actually drags it.
  const [position, setPosition] = useState(() => ({
    x: Math.round((window.innerWidth - window.innerWidth * DEFAULT_WIDTH_RATIO) / 2),
    y: Math.round((window.innerHeight - window.innerHeight * DEFAULT_HEIGHT_RATIO) / 2),
  }));

  const onResizeDrag = useCallback((deltaX: number, deltaY: number) => {
    setSize((prev) => ({
      width: Math.max(MIN_WIDTH, prev.width + deltaX),
      height: Math.max(MIN_HEIGHT, prev.height + deltaY),
    }));
  }, []);

  const onMoveDrag = useCallback((deltaX: number, deltaY: number) => {
    setPosition((prev) => ({
      x: Math.min(
        Math.max(prev.x + deltaX, MIN_VISIBLE_MARGIN - window.innerWidth),
        window.innerWidth - MIN_VISIBLE_MARGIN,
      ),
      y: Math.min(Math.max(prev.y + deltaY, 0), window.innerHeight - MIN_VISIBLE_MARGIN),
    }));
  }, []);

  // 011-canvas-connector-popout, spec FR-011: its own local selection/box-height state,
  // separate from `WorkspacePage.tsx`'s — selecting/connecting here doesn't drive columns 2/3
  // (only column 4's own selection does, unchanged); this pop-out is an additional,
  // independently-usable view, not a replacement selection source (research.md §3).
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  // `ArchitectureDiagramPanel` requires this callback (multi-select order tracking), but
  // nothing in the pop-out currently consumes the ordered id list itself — unlike column 2's
  // "Connect" button, there's no connector-creation control inside the pop-out to pre-populate
  // (spec: connector creation stays consolidated at column 2 only).
  const [, setSelectedNodeIds] = useState<string[]>([]);
  const [ownHeights, setOwnHeights] = useState<Record<string, number>>({});

  const reportHeight = useCallback((id: string, height: number) => {
    setOwnHeights((prev) => (prev[id] === height ? prev : { ...prev, [id]: height }));
  }, []);

  const diagramSelection = selectedServiceId
    ? { kind: "service" as const, id: selectedServiceId }
    : selectedConnectorId
      ? { kind: "connector" as const, id: selectedConnectorId }
      : selectedCollectionId
        ? { kind: "collection" as const, id: selectedCollectionId }
        : null;

  function deselectAll() {
    setSelectedCollectionId(null);
    setSelectedConnectorId(null);
    setSelectedServiceId(null);
  }

  function selectCollection(id: string) {
    setSelectedCollectionId(id);
    setSelectedConnectorId(null);
    setSelectedServiceId(null);
  }

  function selectConnector(id: string) {
    setSelectedConnectorId(id);
    setSelectedCollectionId(null);
    setSelectedServiceId(null);
  }

  function selectService(skuSelectionId: string, containingCollectionId: string) {
    setSelectedCollectionId(containingCollectionId);
    setSelectedConnectorId(null);
    setSelectedServiceId(skuSelectionId);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal={false}>
      <DialogContent
        overlay={false}
        showCloseButton
        // Found live: `DialogContent`'s entrance-animation classes (`data-open:animate-in`/
        // `zoom-in-95`) get stuck applying their starting scaled/translated keyframe state
        // persistently for a dialog whose position/size are externally managed like this one —
        // see `animated`'s own doc comment on `DialogContent` (`ui/dialog.tsx`) for how this
        // was isolated (removing every other class group first, one at a time, live).
        animated={false}
        // `max-w-none` alone doesn't override `DialogContent`'s base `sm:max-w-lg` (32rem) —
        // found live: `max-w-none` and `sm:max-w-lg` are different "slots" to the `cn`/
        // tailwind-merge engine (unprefixed vs. `sm:`-prefixed), so both survive the merge and
        // `sm:max-w-lg` wins at runtime via ordinary CSS cascade at viewport widths ≥640px,
        // silently capping this dialog's width at 512px regardless of the inline `style` below
        // (that's exactly why only height, which has no equivalent `sm:max-h-*` base class, was
        // ever actually resizable). `sm:max-w-none` neutralizes that specific slot too.
        className="max-w-none sm:max-w-none flex flex-col gap-0 p-2"
        // Explicit `top`/`left`/`transform: none`/`translate: none` (all inline, so they win
        // over the base `top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2` centering classes
        // regardless of tailwind-merge slot-matching — the same lesson as `sm:max-w-none`
        // above) replace `DialogContent`'s default centered placement so the dialog can be
        // dragged (live user report: it could be resized but not moved, making it impossible to
        // keep columns 2/3 reachable while it's open). `translate: "none"` is the one that
        // actually matters — found live, the hard way: Tailwind v4 implements
        // `-translate-x-1/2`/`-translate-y-1/2` via the *standalone* CSS `translate` property,
        // not `transform` (confirmed by diffing every computed style property with/without
        // those classes — `transform` was identical/`none` in both, only `translate` differed).
        // `transform: "none"` alone — even with `!important` — left the box still visually
        // offset by exactly half its own width/height despite `getComputedStyle().transform`
        // correctly reporting `"none"`, because the actual offending property was never
        // `transform` at all.
        style={{
          width: size.width,
          height: size.height,
          top: position.y,
          left: position.x,
          transform: "none",
          translate: "none",
        }}
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogTitle className="sr-only">Architecture canvas (enlarged view)</DialogTitle>
        <PopoutDragHandle onDrag={onMoveDrag} />
        {/* `ArchitectureDiagramPanel` sizes its own canvas box internally (its own
            `diagramHeight` state, defaulting to 640px, adjustable via its own
            `DiagramResizeHandle`) rather than filling a parent container — the same as it does
            in column 4 today. This wrapper just gives it room to render at whatever size it
            currently is and scrolls if it's taller than the dialog's own current size, rather
            than clipping or visually breaking out of the dialog's bounds. */}
        <div className="relative min-h-0 flex-1 overflow-auto">
          <ReactFlowProvider>
            <ArchitectureDiagramPanel
              architectureId={architectureId}
              collections={collections}
              connectors={connectors}
              ownHeights={ownHeights}
              reportHeight={reportHeight}
              diagramSelection={diagramSelection}
              onSelectedNodeIdsChange={setSelectedNodeIds}
              onSelectCollection={selectCollection}
              onSelectConnector={selectConnector}
              onSelectService={selectService}
              onDeselectAll={deselectAll}
              onCreateConnector={onCreateConnector}
              onUpdateCollectionParent={onUpdateCollectionParent}
              onRejectedNesting={onRejectedNesting}
              onRefresh={onRefresh}
              // `onOpenPopout` deliberately omitted — this is already the pop-out; see its
              // doc comment on `ArchitectureDiagramPanelProps`.
            />
          </ReactFlowProvider>
        </div>
        {/* Positioned relative to `DialogContent` itself (a `fixed`-positioned ancestor, a
            valid containing block for `absolute`), not the scrollable wrapper above, so it
            stays anchored to the dialog's own visible corner regardless of inner scroll. */}
        <PopoutResizeHandle onDrag={onResizeDrag} />
      </DialogContent>
    </Dialog>
  );
}
