import { ReactFlowProvider } from "@xyflow/react";
import { useCallback, useRef, useState } from "react";

import { type Collection, type DataConnector } from "../../api/client";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { ArchitectureDiagramPanel } from "./ArchitectureDiagramPanel";

const DEFAULT_WIDTH_RATIO = 0.9;
const DEFAULT_HEIGHT_RATIO = 0.85;
const MIN_WIDTH = 480;
const MIN_HEIGHT = 360;

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

  const onResizeDrag = useCallback((deltaX: number, deltaY: number) => {
    setSize((prev) => ({
      width: Math.max(MIN_WIDTH, prev.width + deltaX),
      height: Math.max(MIN_HEIGHT, prev.height + deltaY),
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
        className="max-w-none gap-2 p-2"
        style={{ width: size.width, height: size.height }}
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogTitle className="sr-only">Architecture canvas (enlarged view)</DialogTitle>
        {/* `ArchitectureDiagramPanel` sizes its own canvas box internally (its own
            `diagramHeight` state, defaulting to 640px, adjustable via its own
            `DiagramResizeHandle`) rather than filling a parent container — the same as it does
            in column 4 today. This wrapper just gives it room to render at whatever size it
            currently is and scrolls if it's taller than the dialog's own current size, rather
            than clipping or visually breaking out of the dialog's bounds. */}
        <div className="relative h-full overflow-auto">
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
              onOpenPopout={() => {
                /* Already the pop-out itself — no nested pop-out affordance needed. */
              }}
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
