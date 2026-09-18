# Research: User Accounts, Administration, and Architecture Sharing

**Input**: spec.md's FR-001–FR-031, Assumptions, Clarifications. **Method**: a research pass over the live codebase — backend identity/auth surface (`api/deps.py`, `models/orm.py`), backend migration precedent (`db/migrations/versions/`), and frontend identity/persistence and column-1 conventions (`api/client.ts`, `pages/WorkspacePage.tsx`, `components/workspace/ProviderArchitecturePanel.tsx`). All findings below are grounded in file:line citations gathered during that pass.

## 1. Today's "identity" is already a bearer-token User id — extend it, don't replace it

**Decision**: The existing `User` ORM model (`backend/src/models/orm.py:27-35`) and `get_current_user` dependency (`backend/src/api/deps.py:25-47`) already give every browser a real, distinct, backend-persisted `User` row — the frontend just generates a random UUID once (`frontend/src/api/client.ts:28-35`, `getUserId()`), stores it in `localStorage`, and sends it as `Authorization: Bearer <uuid>`; `get_current_user` lazily creates the row if it doesn't exist yet. This feature does not replace that mechanism — it extends the `User` row with `username`, `password_hash`, `is_active`, `is_admin` (all nullable/defaulted, so today's anonymous rows remain valid with `username IS NULL`), and repurposes the *value* stored under the client's identity `localStorage` key: instead of always being the one permanent per-browser guest UUID, it becomes whichever `User.id` is the browser's "current identity" — the guest UUID by default, or a named user's row id after login (§3).

**Rationale**: The spec's own Assumptions ("self-service password changes... out of scope", "no interface... for granting admin rights", password storage as "a standard one-way hash") describe a deliberately lightweight v1, consistent with `deps.py`'s own docstring ("defers an actual login/session system to a later feature"). Building a parallel session/cookie system alongside the existing bearer-identity mechanism would be two competing identity systems in one app — a Principle VI violation with no current requirement forcing it.

**Alternatives considered**: A new session-cookie + server-side session store — rejected as materially more infrastructure (cookie handling, CSRF, session expiry) than this spec asks for, and contradicts the doc's own explicit deferral ("in later versions we will introduce better security via a system like Supabase").

## 2. Password hashing: stdlib `hashlib.pbkdf2_hmac`, no new dependency

**Decision**: Hash passwords with `hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)` (Python stdlib — already available, no new pip dependency), salt via `secrets.token_hex(16)`. Store as a single string `"pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"` in the new `password_hash` column. The Admin table's "last 4 characters of the hash" (FR-009) reads the last 4 characters of that whole stored string.

**Rationale**: The spec explicitly scopes this as "sufficient for now" (doc: "in later versions we will introduce better security via a system like Supabase") and Assumptions confirm "a standard one-way hash," not a specific algorithm. `hashlib.pbkdf2_hmac` is a real, salted, iterated one-way hash already in the Python standard library — it satisfies the requirement without adding `passlib`/`bcrypt` as a new backend dependency (Principle VI: no new dependency not justified by a current requirement more specific than "some hash").

**Alternatives considered**: `passlib[bcrypt]` — the more conventional production choice, but a new dependency for a feature the spec itself frames as a deliberately temporary v1; deferred until an actual production-security pass (matching the doc's own Supabase remark). Plain reversible storage — rejected outright, the spec requires "encrypted"/hashed storage (FR-010).

## 3. Persisted logged-in identity (FR-019a): same `localStorage` key, new meaning

**Decision**: `frontend/src/api/client.ts`'s `getUserId()` (`client.ts:28-35`) is generalized into a `getCurrentIdentityId()` / `setCurrentIdentityId(id)` pair over the *same* `localStorage` key (`cloud-pricing-user-id`), plus a second key holding the permanent per-browser guest id (seeded once, never overwritten — the value `getUserId()` used to always return). On login success, `setCurrentIdentityId(user.id)` overwrites the "current identity" key with the logged-in user's row id; "change user" and a failed login leave it untouched; explicit "change user" → guest reverts it to the stored guest id. Every subsequent request's `Authorization: Bearer <id>` (and thus every backend permission/ownership check) is driven by this one value.

**Rationale**: `localStorage` (unlike `sessionStorage`) already persists across reloads and browser restarts by construction — exactly the guarantee the Clarification asked for ("mirroring how the guest-mode identity is already persisted in that browser today," FR-019a's own wording). No new persistence mechanism, cookie, or expiry logic is needed; the only change is *what* gets written to the existing key and *when*.

**Alternatives considered**: An HTTP-only session cookie set by the backend — the more conventional real-auth pattern, but requires new backend session-management code and doesn't fit the existing bearer-token-is-the-identity model without a larger rework; rejected for the same reason as §1.

## 4. Admin authorization: a new `require_admin` dependency layered on `get_current_user`

**Decision**: Add `require_admin` to `backend/src/api/deps.py`, built on the existing `CurrentUser` dependency (`deps.py:50`): if `not user.is_active`, raise `401` (closes the deactivation-enforcement edge case — "takes effect on next authentication check"); if `not user.is_admin`, raise `403`. All new `/admin/...` routes depend on it. The frontend's Admin-tab visibility (FR-003) and person-icon state are driven by a new `GET /auth/me` (contracts/api.md) returning the current identity's `username`/`is_admin`/`is_active`, called once on load and after every login/change-user/logout.

**Rationale**: Matches the existing dependency-injection convention in `deps.py` exactly (`CurrentUser = Annotated[User, Depends(get_current_user)]`) rather than introducing a different authorization pattern (e.g., a decorator or middleware) for just this one feature.

**Alternatives considered**: A roles/permissions table — rejected as over-engineered for the spec's single boolean `is_admin` flag and single-admin-account Assumption (Principle VI).

## 5. Deep-copy import: a new service function, mirroring existing cascade-delete relationships

**Decision**: Add `import_architecture(session, source: Architecture, new_owner: User, new_name: str) -> Architecture` to a new `backend/src/services/architecture_import.py`. It creates a new `Architecture` row (`user_id=new_owner.id`, `name=new_name`, `is_public=False`, fresh id), then walks `source.collections` (already ordered by `created_at` per the existing relationship config, `orm.py:105-111`) creating new `Collection` rows with fresh ids and remapped `parent_collection_id` (via an old-id→new-id map, since nested VPC/Application pairs must keep their relative nesting), then new `SKUSelection` rows per collection, then new `DataConnector` rows with remapped `from_collection_id`/`to_collection_id`. All in one transaction.

**Rationale**: The existing `Collection`→`SKUSelection` and `Architecture`→`Collection`/`DataConnector` relationships already use `cascade="all, delete-orphan"` (`orm.py:52-58, 108-112`), confirming these are the exact nested object graphs "collections, connectors, and service selections" (FR-029) must span — the import just needs to *clone* that same graph shape instead of deleting it. A remap table is required (not a raw dict-copy) because nested Application→VPC `parent_collection_id` references must point at the *new* cloned VPC row, not the original's id.

**Alternatives considered**: A raw SQL `INSERT ... SELECT` bulk clone — rejected, harder to remap `parent_collection_id`/`from_collection_id`/`to_collection_id` correctly across the id-remap boundary than an explicit Python walk, for a graph this small (Principle VI: no need for bulk-SQL performance work at this scale).

## 6. Default Admin seeding: an Alembic data migration, matching the 010 backfill precedent

**Decision**: The new migration (`backend/src/db/migrations/versions/0004_user_accounts_sharing.py`) that adds the new `users`/`architectures` columns also inserts one row: `username='Admin', password_hash=<pbkdf2 hash of the literal 'admin123', computed at migration-authoring time>, is_active=true, is_admin=true`, guarded by `WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'Admin')` so re-running migrations (or a fresh test DB) never produces duplicates.

**Rationale**: `0003_collection_region.py` already established the precedent of baking a literal, migration-authored value into a data-migration `UPDATE`/`INSERT` (research.md §1 of 010) rather than adding app-startup seeding code — "the first time the system initializes" (FR-012) is exactly what a migration guarantees, with no new startup-hook mechanism needed.

**Alternatives considered**: A `@app.on_event("startup")` seeding check in `main.py` — rejected, introduces a second place ("did this seed run?") that must independently guard against duplicate seeding, when the migration mechanism already provides exactly-once semantics.

## 7. Default-admin "cannot be deactivated/purged" is a service-layer check, not a DB constraint

**Decision**: `PATCH /admin/users/{id}` and `DELETE /admin/users/{id}` both check `if user.username == "Admin": raise HTTPException(403, ...)` in the route/service layer before applying the change.

**Rationale**: Mirrors the existing pattern in `orm.py` where business rules that can't be expressed as a single-row `CHECK` (e.g., "parent must actually be type=vpc," `orm.py:8-9`) are enforced in the service layer, not the schema. A DB-level "protect this one row" rule (e.g., a trigger) would be unprecedented complexity in this codebase for a single hardcoded exception.

**Alternatives considered**: A `is_protected` boolean column instead of matching on `username == "Admin"` — considered, and adopted instead as `is_default_admin` is simpler to reason about than gating on a magic string long-term; **superseded by data-model.md**, which specifies the boolean column as the actual design (avoids relying on the username being immutable/unique-forever as the source of truth).

## 8. Tabs shell: a new top-level wrapper around the existing `WorkspacePage`, not inside it

**Decision**: Add a new `frontend/src/components/layout/TopTabs.tsx` (or similar) rendered by `App.tsx` above the existing `<Routes>` (`App.tsx:16-19`), with three tabs — "Cloud Pricing" (renders the existing route tree unchanged), "Trends" (disabled `<Button disabled>` placeholder, no route), "Admin" (a new route/page, only rendered/linked when `GET /auth/me` says `is_admin`). The person icon (FR-014) lives in this same new top-level shell, not inside `ProviderArchitecturePanel.tsx`'s column-1 header, since it must be visible regardless of which tab is active.

**Rationale**: `App.tsx` today renders exactly one page (`WorkspacePage`) with no chrome above it (`App.tsx:14-21`) — there is no existing tab/shell component to extend. Keeping the new shell as a thin wrapper (not folded into `WorkspacePage`) matches Principle VI: the existing five-column workspace and its extensive internal state (`WorkspacePage.tsx`) are untouched by this feature except for column 1's sharing/import additions (§9).

**Alternatives considered**: Adding tab state as new `WorkspacePage` internal state — rejected, conflates page-level navigation with the workspace's existing column/selection state for no benefit.

## 9. Column-1 sharing/import additions land in `ProviderArchitecturePanel.tsx`, reusing its existing list-item shape

**Decision**: The public/private icon (FR-020/021) is added next to the existing delete button inside the `expanded` list item (`ProviderArchitecturePanel.tsx:176-193`); the "Import" action (FR-023) is added next to the existing "AWS Architectures" heading (`ProviderArchitecturePanel.tsx:158-161`). The delete button's red color + "Click to remove" tooltip (FR-030) is a styling/tooltip-text change to the existing `✕` button (`ProviderArchitecturePanel.tsx:185-192`) — no new component. Per §research finding: the create-architecture control (`ProviderArchitecturePanel.tsx:215-249`) is **already** positioned after the architecture list rather than before it, so when the list is empty the control already renders directly under the heading — FR-031 is already satisfied by the existing layout and needs no structural change, only confirmation via quickstart.md Scenario 5.

**Rationale**: `ProviderArchitecturePanel.tsx` is already the single owner of column 1's architecture list and its per-row controls; adding sharing/import affordances here keeps one panel responsible for one column, matching every prior column-1 change's convention (e.g., 009's collapse-state work cited in the component's own docstring).

**Alternatives considered**: A separate `ImportDialog`-only component reusing the existing `ui/dialog.tsx` `Dialog` primitive (010's `RegionSelectDialog.tsx` precedent, `components/workspace/RegionSelectDialog.tsx`) for the Import list and the copy-naming prompt — **adopted**, not rejected: the Import list/naming-prompt UI itself is a new dialog component (`ImportArchitectureDialog.tsx`), triggered from `ProviderArchitecturePanel.tsx`, following the exact `Dialog`-reuse precedent 010 established.
