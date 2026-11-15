# Contract: Agent API Changes in 025

Additions to 023's and 024's `contracts/agent-api.md`. All routes are under `/api/v1`, use the
Bearer header, and are defined with Pydantic models (Principle IV).

## Stream: new events

On `POST /agent/session/messages` and `…/retry`:

| `event` | `data` |
|---|---|
| `proposal` | `AgentProposalOut` (below), sent when a `propose_*` operation succeeds; a later one in the same answer supersedes it |
| `open_architecture` | `{"architecture_id": "…", "name": "Prod Web"}`; the frontend runs the unsaved-work check, then opens it (research R7) |

A proposal created before an `error` is kept.

## `GET /agent/session` (extended)

`AgentSessionDetailOut` gains `proposals: AgentProposalOut[]` in `seq` order. Status fields
(`stale`, `undo`) are computed at read time from the architecture's current fingerprint, so a
refetch after any manual edit shows the change.

## `AgentProposalOut`

```json
{
  "id": "…", "message_id": "…", "seq": 3, "kind": "change",
  "architecture_id": "…", "architecture_name": "Prod Web", "title": "…",
  "status": "pending", "stale": false,
  "items": [{"ref": "P1", "op": "add", "target": "service", "label": "…", "group": "standby",
             "before": null, "after": {"quantity": "744", "term": "on_demand", "region": "…"}}],
  "cost": {"duration": "1_month", "snapshot": {"provider": "aws", "date": "2026-09-24",
           "revision": 1}, "before": {"total": "1588.22", "partial": false},
           "after": {"total": "2310.40", "partial": true}, "difference": "722.18",
           "percent": "45.47", "by_service": [], "by_region": [], "contributions": [],
           "unpriceable": [{"label": "…", "reason": "…"}]},
  "assumptions": [{"kind": "region", "text": "…", "guessed": true}],
  "undo": null,
  "created_at": "…", "decided_at": null
}
```

`undo` once accepted: `{"status": "available" | "undone" | "ended", "can_undo": true,
"can_redo": false, "end_reason": null | "edited" | "superseded" | "session_ended" | "deleted"}`.

## Actions

| Route | Body | Effect | Errors |
|---|---|---|---|
| `POST /agent/proposals/{id}/accept` | `{"architecture_id": "…" \| null, "confirm_restaled": false}` | Applies the target state in one transaction; for create/import builds the architecture. Returns `AgentProposalOut` and, for create/import, the new architecture's id to open | 404 not the user's; 409 not pending, session busy, or the open architecture doesn't match; 409 `stale` with the re-priced proposal when stale and `confirm_restaled` is false; 422 no longer valid (the first failing rule) |
| `POST /agent/proposals/{id}/reject` | `{}` | Status `rejected`; nothing else changes | 404; 409 not pending |
| `POST /agent/proposals/{id}/undo` | `{}` | Applies the before state (create/import: soft delete) | 404; 409 `undo_ended` with the reason, or not the latest accepted, or session busy |
| `POST /agent/proposals/{id}/redo` | `{}` | Applies the after state again | 404; 409 as for undo |

- None of these calls the model or uses a message from the allowance; they work after a limit
  is reached (FR-016). Each adds an activity-log row (data-model.md §5).
- On a stale accept, the response carries the re-priced proposal; the user sees the new figures
  and accepts again with `confirm_restaled: true` (FR-007).
- Error bodies follow the app's existing `{"detail": …}` shape, with one brief, precise sentence
  (for example "Your latest edit means the agent's previous change can no longer be undone.").

## Frontend after an action

The client invalidates the session query and the architecture query, as manual edits do, and
opens the new architecture after accepting a create or import.
