# Phase tracker

Living tracker of the phased build. **A phase does not start until the prior gate passes.**
Each gate = automated smoke test + manual smoke checklist (PRD §9.1, CLAUDE.md golden rule #1).

Status legend: ⬜ pending · 🟡 in-progress · ✅ done · 🟥 blocked

| # | Phase | Status | Gate (automated) | Gate (manual) | Notes |
|---|---|---|---|---|---|
| 0 | Foundations — monorepo, auth, multi-tenancy + RLS | ✅ | ✅ | ✅ (partial — see below) | Completed 2026-05-28 |
| 1 | Forecast engine (standalone) + metrics module | ⬜ | — | — | Highest-risk-first; pure Python, no UI/DB |
| 2 | Core data model & CRUD (Sites/Trials/SoA/etc + OrgSettings) | ⬜ | — | — | |
| 3 | Projections & actuals (TanStack spreadsheet grid) | ⬜ | — | — | Keyboard nav + paste are first-class acceptance criteria |
| 4 | Forecast wiring & views (network grid, per-site chart, metrics view, calendar) | ⬜ | — | — | |
| 5 | Trial setup wizard + AI SoA parsing | ⬜ | — | — | Claude API (vision) |
| 6 | Admin settings, exports & commercialization polish | ⬜ | — | — | Render deploy lands here |

---

## Phase 0 — Foundations ✅

**Started:** 2026-05-28 · **Completed:** 2026-05-28

### Delivered
- Monorepo: `/engine` (uv placeholder pkg w/ pytest), `/backend` (FastAPI), `/frontend` (Vite+React+TS+Tailwind), `/docs`
- Docker Compose: Postgres 16 (host port `55432` — avoids collision with Homebrew Postgres / other dev containers), Redis 7, backend, arq worker stub, frontend dev server
- Postgres init script (`docker/postgres-init/01-roles.sql`) creates the two-role split: `app_owner` (BYPASSRLS, used by Alembic) and `app_user` (RLS-enforced runtime role)
- Auth: email/password, Argon2id (`argon2-cffi`), signed-cookie sessions (`itsdangerous`, HttpOnly, SameSite=Lax, 14-day expiry)
- Multi-tenancy: `org_id` on every domain table via `OrgScopedMixin`; Postgres RLS policies on `users` and `organizations` reading `current_setting('app.current_org_id')`; `SET LOCAL` per request via `set_tenant()` in `app/db.py`
- Roles: `org_admin | ops_lead | site_manager | viewer` with `require_role(...)` dep; admin-only stub route at `/orgs/admin-only` proving the gate
- GitHub Actions CI: engine + backend (w/ Postgres service container) + frontend jobs in parallel
- Living docs: `phase.md` and `architecture.md`

### Gate — automated smoke test ✅

`backend/tests/test_rls_isolation.py` (run 2026-05-28):

```
tests/test_health.py::test_healthz PASSED                                [ 25%]
tests/test_rls_isolation.py::test_two_orgs_isolated_via_api PASSED       [ 50%]
tests/test_rls_isolation.py::test_rls_blocks_cross_org_reads_at_db_level PASSED [ 75%]
tests/test_rls_isolation.py::test_role_gating_blocks_non_admin PASSED    [100%]
4 passed
```

The load-bearing assertion: with the tenant bound to Org A's id and querying directly as `app_user` (bypassing the API layer), Org B's rows are invisible — proving Postgres RLS, not application code, is the enforcement boundary. CLAUDE.md golden rule #6 is structurally protected.

### Gate — manual smoke checklist ✅ (partial — see notes)

Exercised end-to-end against a running stack on 2026-05-28:

- [x] `docker compose up -d db` brings Postgres healthy with both roles (`app_owner` BYPASSRLS, `app_user` RLS-enforced) — verified with `\du`
- [x] `alembic upgrade head` applies the `0001_init_orgs_users_rls` migration cleanly
- [x] `uvicorn app.main:app` boots, `GET /healthz` returns `{"status":"ok"}`
- [x] `POST /orgs` creates an org + admin (RLS-friendly: tenant bound to fresh org_id before insert)
- [x] `POST /auth/login` sets a `vfp_session` cookie with `HttpOnly`, `SameSite=Lax`, signed payload + timestamp; HTTP 204
- [x] `GET /auth/me` round-trips the cookie and returns the signed-in user (id, org_id, email, name, role)
- [x] `GET /orgs/me` returns the signed-in org (RLS-scoped — invisible from other orgs)
- [x] `GET /orgs/admin-only` returns 200 for `org_admin`; the role gate test confirms 403 for non-admins
- [x] Frontend builds clean (`pnpm run build` — TypeScript and Vite green)
- [ ] **Not yet exercised:** browser-rendered login flow with visual confirmation of the Tailwind UI. Built and bundles, but a human still needs to open `http://localhost:5173`, type into the form, and confirm the cookie shows up in DevTools. Recommended as the first thing to do at the top of the Phase 1 session.

### Open items deferred to later phases
- `OrgSettings` table → Phase 2
- Render deployment → Phase 6
- Arq worker logic → Phase 5 (container is up but idle)
- Browser-rendered visual smoke of the frontend login → first thing to verify at the start of Phase 1
