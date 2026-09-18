# Data Model: User Accounts, Administration, and Architecture Sharing

Source: spec.md Key Entities + Functional Requirements; grounded against `backend/src/models/orm.py` and `backend/src/models/schemas.py` (see research.md for file:line citations).

## User (modified)

Existing entity (`backend/src/models/orm.py:27-35`) — today just `id`, `created_at`, and the `architectures` relationship, lazily created per browser by `get_current_user` (research.md §1).

| Field | Type | Notes |
|---|---|---|
| `username` | `str \| None`, **unique when not null** (new) | `NULL` for today's anonymous guest rows (unchanged behavior — research.md §1); set exactly once, at admin creation (FR-005), for a named account. Uniqueness enforced by a partial unique index (`WHERE username IS NOT NULL`) so multiple `NULL` guest rows remain valid. |
| `password_hash` | `str \| None` (new) | `NULL` until the Admin sets one (FR-009) or the user creates one on first login (FR-017). Format `"pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"` (research.md §2). Never the plaintext password (FR-010). |
| `is_active` | `bool`, default `True` (new) | FR-007/FR-008. Checked by `get_current_user`/`require_admin` (data-model.md's Auth section below) on every request — an already-open session is not instantly invalidated (spec Edge Cases), only blocked on its *next* auth check. |
| `is_admin` | `bool`, default `False` (new) | FR-003. Exactly one row (`is_default_admin=True`, below) is admin at seed time; nothing in this version grants it to another row (spec Assumptions). |
| `is_default_admin` | `bool`, default `False` (new) | Set `True` only on the seeded Admin row (research.md §7/§6). Distinct from `is_admin` so a future admin-promoted user is still purgeable/deactivatable — only the one seeded row is protected (FR-013). |

**Seeding** (FR-012): exactly one row with `username='Admin', is_admin=True, is_active=True, is_default_admin=True`, and a working `password_hash` for the literal default password `admin123`, inserted by the new migration (research.md §6) guarded against re-insertion.

**Protection rule** (FR-013), enforced in the admin service layer, not the schema:
```
if user.is_default_admin:
    reject PATCH .../active and DELETE .../{id}
```

**Auth check** (extends `get_current_user`, `deps.py:25-47`; new `require_admin`):
```
get_current_user(token):
    user := User row for token (lazily created if absent, as today)
    if user.username is not NULL and not user.is_active:
        401  # FR-008, Edge Cases: deactivation takes effect on next auth check
    return user

require_admin(user = get_current_user()):
    if not user.is_admin:
        403
    return user
```

## Architecture (modified)

Existing entity (`backend/src/models/orm.py:38-59`) — `id`, `user_id` (owner), `provider`, `name`, `deleted_at`, timestamps.

| Field | Type | Notes |
|---|---|---|
| `is_public` | `bool`, default `False` (new) | FR-020. Owner-only toggle (contracts/api.md). Never `True` for an architecture owned by a guest row (`user.username IS NULL`) — enforced server-side (FR-022), since guests have no durable identity to attribute a public share to. |

**Visibility rule** (FR-022), enforced server-side on the `is_public` toggle endpoint:
```
if owner.username is NULL:  # guest-owned
    reject the toggle entirely (this architecture can never become public)
```

**Import** (FR-029) produces a new, independent `Architecture` row — see "Import Copy" below. `deleted_at` (existing soft-delete) is orthogonal: only non-deleted (`deleted_at IS NULL`), public, non-own architectures are ever importable (contracts/api.md).

## Import Copy (derived operation, not a new entity)

Not a new table — a service-layer deep clone (research.md §5) of the existing `Architecture → Collection → SKUSelection` and `Architecture → DataConnector` graphs (`orm.py:38-144`):

```
import_architecture(source, new_owner, new_name):
    new_arch := Architecture(user_id=new_owner.id, name=new_name, provider=source.provider, is_public=False)
    id_map := {}  # old Collection.id -> new Collection.id
    for collection in source.collections (existing created_at order, orm.py:105-111):
        new_collection := clone(collection, architecture_id=new_arch.id,
                                 parent_collection_id=id_map.get(collection.parent_collection_id))
        id_map[collection.id] := new_collection.id
        for sku in collection.sku_selections:
            clone(sku, collection_id=new_collection.id)
    for connector in source.connectors:
        clone(connector, architecture_id=new_arch.id,
              from_collection_id=id_map[connector.from_collection_id],
              to_collection_id=id_map[connector.to_collection_id])
    return new_arch
```

Parent collections are guaranteed to be cloned before their children read `id_map`, since `source.collections` is walked in `created_at` order and a child's `parent_collection_id` always refers to a VPC created earlier (nesting can only be added to an already-existing VPC — spec 002's own invariant). The copy has no reference back to `source` (FR-029, Edge Cases: later edits/deletes/purges of the source never affect it).

## Current Identity (frontend-only concept, no new table)

Not a database table (spec's own Key Entities framing). A single `localStorage` value (research.md §3) naming which `User.id` — the permanent per-browser guest id, or a logged-in user's row id — is sent as the `Authorization: Bearer` token on every request. Persists across reloads/restarts by construction (FR-019a) since it's `localStorage`, not `sessionStorage`. Exposed to the frontend via `GET /auth/me` (contracts/api.md), which resolves the bearer token to `{username, is_admin, is_active}` (or `username: null` for a guest row) so the person icon and tab bar can render the right state without the frontend tracking login state independently of the backend.
