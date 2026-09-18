# API Contracts: User Accounts, Administration, and Architecture Sharing

All schema changes below are Pydantic-native (`backend/src/models/schemas.py`) per Constitution Principle IV — `check-api-types` MUST pass after each change, regenerating the corresponding TypeScript types consumed by `frontend/src/api/client.ts`.

## 1. `GET /auth/me` (new)

Resolves the current bearer token to the current identity's user-facing state (data-model.md's Current Identity). Called on load and after every login/change-user/logout so the tab bar and person icon never rely on client-tracked login state alone.

**Response** `CurrentUserOut`:
```jsonc
{ "id": "uuid", "username": "string | null", "is_admin": "bool", "is_active": "bool" }
```
`username: null` means guest (FR-016). Never `401` on its own — a brand-new bearer token still lazily creates a guest row (existing `get_current_user` behavior, unchanged).

## 2. `POST /auth/check-username` (new)

Lets the login popup (FR-017) decide which step to show next, without yet attempting a login.

**Request**: `{ "username": "string" }`

**Response**: `{ "exists": "bool", "has_password": "bool" }` — both `false` if the username doesn't exist.

## 3. `POST /auth/login` (new)

**Request** `LoginRequest`: `{ "username": "string", "password": "string" }`

**Server behavior** (FR-017/FR-018/FR-008):
- Username doesn't exist → `401` (generic, no detail distinguishing why — FR-018's "no error message" is a frontend behavior: the popup just closes on any `401`).
- Username exists, `password_hash IS NULL` → this call **sets** the password (first-time creation) and logs in. (The frontend's "create a password" prompt and "enter your password" prompt both call this same endpoint — the server, not the client, knows which case applies.)
- Username exists, `password_hash` set, `is_active = false` → `401` (FR-008 — deactivated reads identically to wrong-password).
- Username exists, `password_hash` set, `is_active = true`, password doesn't match → `401`.
- Username exists, `password_hash` set, `is_active = true`, password matches → success.

**Response on success** `CurrentUserOut` (same shape as `GET /auth/me`). On any failure: `401`, empty/generic body — the frontend never inspects the failure reason (FR-018).

**Frontend behavior on success**: overwrite the current-identity `localStorage` value with the returned `id` (research.md §3) so it persists across reloads (FR-019a).

## 4. `GET /admin/users` (new, `require_admin`)

Lists every **named** account (`username IS NOT NULL`) — anonymous guest rows never appear here (FR-004).

**Response**: `AdminUserOut[]`:
```jsonc
[{ "id": "uuid", "username": "string", "is_active": "bool", "has_password": "bool",
   "password_hash_suffix": "string | null", "is_admin": "bool", "is_default_admin": "bool" }]
```
`password_hash_suffix` is the last 4 characters of the stored `password_hash` string (`null` if `has_password` is `false`) — the UI never receives, and the server never sends, anything password-derived beyond those 4 characters (FR-009/FR-010).

## 5. `POST /admin/users` (new, `require_admin`)

**Request**: `{ "username": "string" }` — the only required field (FR-005); `is_active` defaults `true`, no password.

**Server behavior**: `400` if `username` already exists (case-sensitive exact match — FR-006).

**Response**: `201` + `AdminUserOut`.

## 6. `PATCH /admin/users/{user_id}` (new, `require_admin`)

**Request**: `{ "is_active": "bool" }`

**Server behavior**: `403` if the target's `is_default_admin` is `true` (FR-013). Otherwise updates `is_active` (FR-007); does not touch any Architecture or other data owned by the user (FR-008).

**Response**: `200` + updated `AdminUserOut`.

## 7. `PUT /admin/users/{user_id}/password` (new, `require_admin`)

Backs both the table's "Create" and "Update" password actions (FR-009/FR-010) — same endpoint either way, since the only difference is whether `password_hash` was already set.

**Request**: `{ "password": "string" }` — non-empty (spec Assumptions: no complexity rules beyond non-empty).

**Response**: `200` + updated `AdminUserOut` (so the UI can refresh the displayed hash suffix and the action-button label in one round trip).

## 8. `DELETE /admin/users/{user_id}` (new, `require_admin`)

Purges exactly one user and everything they own (FR-011).

**Server behavior**: `403` if the target's `is_default_admin` is `true` (FR-013). Otherwise, in one transaction: deletes every `Architecture` owned by the user (cascading to its `Collection`/`DataConnector`/`SKUSelection` rows via the existing `cascade="all, delete-orphan"` relationships, `orm.py:52-58,108-112`), then deletes the `User` row itself. No other user's rows are touched (SC-002).

**Response**: `204`.

## 9. `PATCH /architectures/{architecture_id}` (new — no existing update endpoint today)

**Request** `ArchitectureUpdate`: `{ "is_public": "bool" }`

**Server behavior** (FR-020/FR-021/FR-022): caller must own the architecture — **`404`** otherwise (implementation-time correction: matches `get_owned_architecture`'s existing "not found, not 403" convention for a non-owned architecture, `architecture_service.py`, so ownership is never revealed by a distinguishable status code). `403` if the owner is a guest row (`username IS NULL`) — a guest-owned architecture can never be made public (this one *is* a 403, since the caller does own it — the rejection is about the state being requested, not who's asking).

**Response**: `200` + `ArchitectureSummaryOut`, which gains:
```jsonc
{ "...": "unchanged fields (id, name, provider)", "is_public": "bool" }
```

## 10. `GET /architectures/importable` (new)

Backs the Import list (FR-023–FR-026). Returns every other user's public, non-deleted architecture, pre-grouped and pre-sorted server-side (so the frontend does no sorting/grouping logic of its own — matches the existing `ArchitectureSummaryOut`-list convention where ordering is server-authoritative).

**Response**: `ImportableArchitecturesOut`:
```jsonc
{
  "groups": [
    {
      "owner_username": "string",
      "architectures": [{ "id": "uuid", "name": "string" }]   // sorted by name (FR-025)
    }
  ]
  // groups sorted alphabetically by owner_username, except the group whose
  // owner_username == "Admin" (if present) is always first (FR-024).
  // An owner with zero public architectures is omitted entirely (FR-026).
  // The caller's own architectures are never included, even if public.
}
```

**Server behavior**: `[]`/empty `groups` for a guest caller is a valid response, but the frontend never calls this endpoint for a guest (FR-027) — the Import action itself isn't rendered.

## 11. `POST /architectures/{architecture_id}/import` (new)

**Request** `ArchitectureImportRequest`: `{ "name": "string" }` — the confirmed name from the naming prompt (FR-028), already defaulted to `"My {original name}"` client-side before the user confirms/edits it.

**Server behavior** (FR-029): `404` if the target architecture doesn't exist, isn't public, or belongs to the caller. Otherwise runs `import_architecture` (data-model.md) and returns the new architecture. Caller must be a named user (guests never see the Import action — FR-027 — but the endpoint itself also rejects a guest caller with `403` as a defensive backend check).

**Response**: `201` + `ArchitectureSummaryOut` for the new copy.

## Frontend API client changes (`frontend/src/api/client.ts`)

- `getCurrentIdentityId()` / `setCurrentIdentityId(id)` — replace the current always-guest `getUserId()` (research.md §3); a new, separate `getGuestId()` keeps the one permanent per-browser guest id that `setCurrentIdentityId` reverts to on logout/"change user"-to-guest.
- `getCurrentUser()` — new, calls `GET /auth/me`.
- `checkUsername(username)` — new, calls `POST /auth/check-username`.
- `login(username, password)` — new, calls `POST /auth/login`; on success, calls `setCurrentIdentityId`.
- `listAdminUsers()`, `createAdminUser(username)`, `setAdminUserActive(id, isActive)`, `setAdminUserPassword(id, password)`, `deleteAdminUser(id)` — new, map 1:1 to the `/admin/users` endpoints above.
- `setArchitecturePublic(architectureId, isPublic)` — new, calls `PATCH /architectures/{id}`.
- `listImportableArchitectures()` — new, calls `GET /architectures/importable`.
- `importArchitecture(architectureId, name)` — new, calls `POST /architectures/{id}/import`.
