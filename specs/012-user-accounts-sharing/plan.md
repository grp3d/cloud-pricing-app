# Implementation Plan: User Accounts, Administration, and Architecture Sharing

**Branch**: `012-user-accounts-sharing` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-user-accounts-sharing/spec.md`

## Summary

Drawn from `docs/functionality_2026-09-18.md` plus one clarification (spec.md's Clarifications section — logged-in identity persists across reloads/restarts): turn today's anonymous, per-browser guest identity into real, backend-persisted, admin-managed user accounts, without discarding the existing bearer-token-is-the-identity mechanism (research.md §1). Adds a top-level tab shell (Cloud Pricing / disabled Trends / role-gated Admin), an Admin-tab user-management table (create/activate/password/purge), a top-left person icon driving login/guest/change-user, architecture public/private sharing, a grouped/sorted Import flow that deep-copies a shared architecture, and two small column-1 polish items. The design deliberately keeps the existing lightweight `Authorization: Bearer <user-id>` identity model (extending the `User` row itself, not building a parallel session system) and uses stdlib password hashing — both chosen to match the spec's own "deliberately temporary v1" framing (research.md §1–§2) rather than introducing new session or crypto dependencies ahead of an actual production-security pass.

## Technical Context

**Language/Version**: Python 3.12 (backend, unchanged); TypeScript ~5.6, React 18.3, Vite 5.4 (frontend, unchanged) — both `frontend/` and `backend/` are touched.

**Primary Dependencies**: No new npm/pip dependency. Backend reuses FastAPI + Pydantic + SQLAlchemy/Alembic (existing); password hashing uses the Python stdlib `hashlib`/`secrets` (research.md §2), not a new library. Frontend reuses the existing `Dialog` primitive (`components/ui/dialog.tsx`) for the login popup, password-set popup, and Import dialog, following 010's `RegionSelectDialog.tsx` precedent (research.md §9); React Router (`react-router-dom`, existing) gains one new route for the Admin page.

**Storage**: PostgreSQL (existing) — schema changes only, no new tables: `users` gains `username`, `password_hash`, `is_active`, `is_admin`, `is_default_admin`; `architectures` gains `is_public` (data-model.md). One data migration also seeds the default Admin row (research.md §6). Parquet-via-DuckDB (existing, read-only) is untouched — this feature has no pricing-data surface.

**Testing**: Backend — pytest, test-first (Constitution Principle V) for: password hashing/verification (`hashlib`-based, new unit test), `require_admin`/`get_current_user`'s active-check (extended contract tests alongside a new `test_auth.py`), the `/admin/users` CRUD contract tests (new `test_admin_users.py`, including the default-Admin-is-protected `403` cases and the purge-cascade case), the architecture `is_public` toggle and guest-owner rejection (extended `test_architectures.py`), and `import_architecture`'s deep-copy/remap correctness including nested VPC/Application parent remapping (new `test_architecture_import.py`, real-DB-backed per this repo's no-mocking convention). Frontend — Vitest + Testing Library, test-first for any new pure logic (none of substantial complexity is expected here beyond the existing component-level testing convention, e.g. `ServiceConfigPanel.test.tsx`'s precedent); `claude-in-chrome` live verification against `quickstart.md` for the tab shell, person icon/login popup, Admin table, sharing icon, and Import dialog — all presentational UI with real end-to-end auth/ownership behavior, per Principle V's carve-out.

**Target Platform**: Existing web SPA, desktop-width browsers (unchanged).

**Project Type**: Web application (`backend/` + `frontend/` split) — both sides touched.

**Performance Goals**: No new numeric target. All new queries (admin user list, importable-architectures list) are simple indexed lookups over a small (demo-scale) user/architecture count — not benchmarked further per Constitution Principle VI.

**Constraints**: `check-api-types` MUST stay clean for every schema change in contracts/api.md (Constitution Principle IV). Password hashes MUST never be returned beyond their last-4-character suffix (FR-009/FR-010) — enforced by `AdminUserOut` never including the full `password_hash` field. The default Admin account's protection (FR-013) MUST be enforced server-side (not just a disabled frontend control), since a client bypass must not be able to deactivate/purge it. Deactivation/purge enforcement is next-auth-check, not real-time (spec Edge Cases) — no websocket/polling invalidation is in scope. Existing backend and frontend test suites stay green throughout.

**Scale/Scope**: Two modified tables (`users`, `architectures`), no new tables; roughly a dozen new backend endpoints (`/auth/*`, `/admin/users/*`, two on `/architectures/*`); one new frontend top-level shell (tabs + person icon), one new Admin page, three new dialogs (login/password-set, Import list, import-naming prompt), and additions to the existing `ProviderArchitecturePanel.tsx`. Demo-scale data volume (a handful of admin-managed users, dozens of architectures) per the feature's own stated motivation (docs/functionality_2026-09-18.md's opening line).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Pricing Data Integrity**: N/A/PASS — this feature never reads or writes vendor pricing data; it is entirely about Postgres-owned user/account/sharing data. No price is touched.
- **II. Clear Data-Layer Separation**: PASS — every new field (`User.username`/`password_hash`/`is_active`/`is_admin`/`is_default_admin`, `Architecture.is_public`) is a Postgres attribute of an existing user-defined-data entity (data-model.md); nothing here reads from or writes to the Parquet/DuckDB pricing layer.
- **III. Provider-Extensibility by Design**: PASS — accounts, admin management, and sharing/import are entirely provider-agnostic; nothing in this feature's data model or endpoints references AWS specifically, so it applies unchanged whenever GCP/Azure architectures exist later.
- **IV. Type-Safe Frontend/Backend Contract**: GATE — every new/changed surface in contracts/api.md (`GET /auth/me`, `POST /auth/check-username`, `POST /auth/login`, the five `/admin/users*` endpoints, `PATCH /architectures/{id}`, `GET /architectures/importable`, `POST /architectures/{id}/import`) is Pydantic-native; `check-api-types` MUST pass and regenerate the frontend types each depends on.
- **V. Test-First Development**: GATE — password hashing/verification, the active/admin auth-dependency logic, all `/admin/users` CRUD, the `is_public` toggle's ownership/guest-rejection rules, and `import_architecture`'s deep-copy are all Postgres read/write logic for user-defined objects → NON-NEGOTIABLE test-first (obligations named against specific new test files in Technical Context above). The tab shell, person icon, Admin table UI, sharing icon, and Import dialogs are presentational → tests-after / live-verified per Principle V's carve-out, against quickstart.md.
- **VI. Simplicity & YAGNI**: PASS, with explicit fences carried from research.md: no new session/cookie system, reusing the existing bearer-token-is-the-identity mechanism instead (§1); stdlib password hashing instead of a new `passlib`/`bcrypt` dependency (§2); no roles/permissions table for a single boolean `is_admin` flag (§4); no bulk-SQL clone machinery for a small per-architecture object graph (§5); no app-startup seeding hook when the existing Alembic-migration mechanism already gives exactly-once seeding (§6); no DB trigger/constraint for the single-row default-Admin protection rule, handled in the service layer like this codebase's other cross-row business rules (§7).

No unjustified violations. Complexity Tracking is not needed.

**Post-Design re-check** (after Phase 0/1 artifacts above): every gate still holds against the concrete design. II is confirmed by data-model.md's fields all living on existing Postgres entities with no Parquet touch; III is confirmed by contracts/api.md's endpoints containing no provider-specific naming or logic; IV is discharged by contracts/api.md's explicit request/response shapes for all eleven new/changed surfaces; V's obligations are named against specific files in Project Structure below; VI's fences from research.md all survived into the final data-model.md/contracts/api.md unchanged (e.g., `is_default_admin` as a plain boolean rather than a magic-username check, per research.md §7's own noted supersession). No new violations were introduced while designing data-model.md/contracts/quickstart.md.

## Project Structure

### Documentation (this feature)

```text
specs/012-user-accounts-sharing/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── api.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── db/migrations/versions/
│   │   └── 0004_user_accounts_sharing.py   # NEW — users columns, architectures.is_public, Admin seed row
│   ├── models/
│   │   ├── orm.py                          # User gains username/password_hash/is_active/is_admin/
│   │   │                                    #   is_default_admin; Architecture gains is_public
│   │   └── schemas.py                      # CurrentUserOut, LoginRequest, AdminUserOut,
│   │                                        #   AdminUserCreate, AdminPasswordUpdate,
│   │                                        #   ArchitectureUpdate, ImportableArchitecturesOut,
│   │                                        #   ArchitectureImportRequest; ArchitectureSummaryOut
│   │                                        #   gains is_public
│   ├── api/
│   │   ├── deps.py                         # get_current_user gains is_active check; NEW require_admin
│   │   ├── auth.py                         # NEW — /auth/me, /auth/check-username, /auth/login
│   │   ├── admin_users.py                  # NEW — /admin/users CRUD (require_admin)
│   │   └── architectures.py                # NEW PATCH /{id}; NEW GET /importable, POST /{id}/import
│   └── services/
│       ├── auth_service.py                 # NEW — hash_password/verify_password (research.md §2)
│       └── architecture_import.py          # NEW — import_architecture (data-model.md)
└── tests/
    ├── contract/
    │   ├── test_auth.py                    # NEW — login flows, active-check, persistence semantics
    │   ├── test_admin_users.py             # NEW — CRUD, default-Admin protection, purge cascade
    │   └── test_architectures.py           # extended — is_public toggle, guest-owner rejection,
    │                                        #   importable listing grouping/sorting, import endpoint
    └── unit/
        ├── test_auth_service.py           # NEW — hash/verify round-trip, hash-suffix format
        └── test_architecture_import.py    # NEW — deep-copy graph shape, id-remap correctness

frontend/
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   ├── TopTabs.tsx                 # NEW — Cloud Pricing / Trends (disabled) / Admin tabs
│   │   │   └── IdentityMenu.tsx            # NEW — person icon + guest/username + login/change-user
│   │   ├── auth/
│   │   │   └── LoginDialog.tsx             # NEW — username → create/enter password (reuses ui/dialog.tsx)
│   │   └── workspace/
│   │       ├── ProviderArchitecturePanel.tsx  # sharing icon + Import action + red delete-X/tooltip
│   │       └── ImportArchitectureDialog.tsx   # NEW — grouped/sorted list + naming prompt
│   ├── pages/
│   │   ├── AdminPage.tsx                   # NEW — user-management table
│   │   └── WorkspacePage.tsx               # unchanged except column-1 prop wiring for sharing/import
│   ├── api/client.ts                       # getCurrentIdentityId/getGuestId/setCurrentIdentityId,
│   │                                        #   getCurrentUser, checkUsername, login, admin-user
│   │                                        #   functions, setArchitecturePublic,
│   │                                        #   listImportableArchitectures, importArchitecture
│   └── App.tsx                             # renders TopTabs + IdentityMenu above existing <Routes>;
│                                            #   new /admin route (gated by GET /auth/me's is_admin)
└── tests/unit/
    └── (component tests for the above, tests-after per Principle V's UI carve-out)
```

**Structure Decision**: Existing `backend/` + `frontend/` split (unchanged from 001–011). No new top-level directories. Backend adds two small new route modules (`api/auth.py`, `api/admin_users.py`) rather than folding unrelated concerns into `architectures.py`, matching 010's precedent of a dedicated new module per genuinely new capability (`api/regions.py`). Frontend adds a `components/layout/` directory (new — this is the first feature to need chrome above `WorkspacePage`, per research.md §8) and a `components/auth/` directory for the login/password dialogs, while column-1 sharing/import additions land inside the existing `ProviderArchitecturePanel.tsx` plus one new sibling dialog component, matching research.md §9.

## Complexity Tracking

*No Constitution Check violations requiring justification.*
