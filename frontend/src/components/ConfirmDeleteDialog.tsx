interface Props {
  itemLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A blocking confirm-before-delete prompt, per FR-014/FR-015 ("system MUST prompt for
 * confirmation before deleting"). Deliberately a plain modal — no dialog library needed for
 * one yes/no prompt (Constitution Principle VI). */
export function ConfirmDeleteDialog({ itemLabel, onConfirm, onCancel }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ background: "white", padding: 24, borderRadius: 8, minWidth: 280 }}>
        <p>
          Delete <strong>{itemLabel}</strong>? This can&apos;t be undone from the UI.
        </p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel}>Cancel</button>
          <button onClick={onConfirm} autoFocus>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
