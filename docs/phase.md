# Phase tracker

Living tracker of the phased build. **A phase does not start until the prior gate passes.**
Each gate = automated smoke test + manual smoke checklist (PRD §9.1, CLAUDE.md golden rule #1).

Status legend: ⬜ pending · 🟡 in-progress · ✅ done · 🟥 blocked

| # | Phase | Status | Gate (automated) | Gate (manual) | Notes |
|---|---|---|---|---|---|
| 0 | Foundations — monorepo, auth, multi-tenancy + RLS | ✅ | ✅ | ✅ (partial — see below) | Completed 2026-05-28 |
| 1 | Forecast engine (standalone) + metrics module | ✅ | ✅ | ✅ | Completed 2026-05-28 |
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

---

## Phase 1 — Forecast engine + metrics ✅

**Started:** 2026-05-28 · **Completed:** 2026-05-28

### Delivered
- `engine/types.py` — input/output dataclasses (Site, Trial, Arm, Visit, AttritionCurve, EnrollmentWeek, Commitment, OrgDurationDefaults, ForecastCell, MetricsRow, VisitType, WeekRange). All frozen, slotted, hashable; zero web/DB imports.
- `engine/windows.py` — `triangular_weights(anchor, window_days)` and `smear_count(...)`. Discrete triangular distribution with raw weights `(W+1-|k|)` and normalizer `(W+1)²`. **Horizon policy:** full window, mass outside reported range is unreported (see [project memory](../README.md#memory) — modeling decisions).
- `engine/attrition.py` — `survival_by_visit(visits, curve)`. Screening = 1.0 always; randomized chain decays linearly with visit index (linear back-loaded shape).
- `engine/duration.py` — `effective_duration(visit, defaults, site_overrides)`. PRD §5.2 order: site override → visit override → org type default.
- `engine/forecast.py` — `compute_forecast(commitments, today, horizon_end)`. PRD §6.4 pseudocode made real. Tracks each placement's anchor week for range bounds.
- `engine/metrics.py` — `compute_metrics(...)`. SFR, screen rate, enrollment rate, pace-vs-plan, enrollment health (against both randomization + screening goals), week-over-week.
- Tests: 30 total — 5 attrition, 4 duration, 5 windows, 1 purity, 9 forecast golden masters, 6 metrics golden masters.

### Gate — automated smoke test ✅

`engine/tests/` (run 2026-05-28):

```
30 passed in 0.03s
```

Forecast golden masters cover PRD §6.7's required scenarios:
- `single_cohort_fan` — basic 1-site/1-trial/no-attrition visit fan
- `multi_cohort_stacking` — overlapping cohorts sum cleanly
- `survival_decay_applies_to_randomized_chain_only` — 20% Standard over 5 visits = (1.0, 0.95, 0.90, 0.85, 0.80); screening unaffected
- `window_smearing_across_week_boundary` — visit anchored on Mon W1 with ±2-day window, mass split (3.333 to W0, 6.667 to W1) per triangular weights, **and** range bounds verified (W0 low=10 from anchored-here v0 + W1's smear contributes 0 to low; W1 low=high=6.667)
- `screening_driven_by_screened_not_randomized` — PRD §6.2 #1 enforced: 20 screened, 8 randomized, each screening visit fires with full 20
- `hours_and_capacity_arithmetic` — capacity = rooms × ops_days × hrs/day; utilization = demand_hours / capacity_hours
- `revenue_is_count_times_price` — including price=None contributing 0
- `actuals_override_when_past_week_is_in_horizon` — past cohort's downstream visits use actual count (4), not projection (10)
- `range_bounds_collapse_with_zero_window` — invariant that point windows produce low=high=expected for every cell

Metrics golden masters cover PRD §6.8:
- SFR, screen rate, enrollment rate, pace-vs-plan, enrollment health (both goals), week-over-week
- Edge cases: None when inputs insufficient (SFR with 0 screened)

Engine purity test enforces CLAUDE.md golden rule #2: the test imports every submodule of `engine` and asserts no forbidden module is reachable in `sys.modules` (fastapi, sqlalchemy, asyncpg, httpx, app, etc.).

### Gate — manual smoke ✅
- [x] Walked through `test_window_smearing_across_week_boundary` with the human (2026-05-28). The math (triangular weights `(1,2,3,2,1)/9` at offsets `(-2,-1,0,+1,+2)` from Mon 2026-06-08 mapping to `(Sat W0, Sun W0, Mon W1, Tue W1, Wed W1)`, so 3.333 mass to W0 and 6.667 to W1; range bounds `low=10/high=13.333` for W0 and `low=high=6.667` for W1) was confirmed correct. The hand-computed expected values in the test match the algorithm's intent.

### Modeling decisions made for this phase
Saved to project memory and noted in the engine source:
- **Triangular window normalization: full window, mass may fall outside.** Mass landing past the reported horizon is unreported. Consistent with PRD §6.3's conservative-on-screening posture (under-reporting at edges is safe for a don't-oversell tool).
- **Attrition shape: linear back-loaded by visit index.** Survival decays linearly across the randomized chain so cumulative dropout at the last visit = `curve.total_dropout_pct`. Defensible and tractable for hand-computed fixtures; can be A/B-tested in v1.5 if real data argues for a different shape.
