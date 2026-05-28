# Phase tracker

Living tracker of the phased build. **A phase does not start until the prior gate passes.**
Each gate = automated smoke test + manual smoke checklist (PRD §9.1, CLAUDE.md golden rule #1).

Status legend: ⬜ pending · 🟡 in-progress · ✅ done · 🟥 blocked

| # | Phase | Status | Gate (automated) | Gate (manual) | Notes |
|---|---|---|---|---|---|
| 0 | Foundations — monorepo, auth, multi-tenancy + RLS | ✅ | ✅ | ✅ (partial — see below) | Completed 2026-05-28 |
| 1 | Forecast engine (standalone) + metrics module | ✅ | ✅ | ✅ | Completed 2026-05-28 |
| 2 | Core data model & CRUD (Sites/Trials/SoA/etc + OrgSettings) | ✅ | ✅ | ✅ | Completed 2026-05-28 |
| 3 | Projections & actuals (TanStack spreadsheet grid) | 🟡 | ✅ | _pending_ | Started 2026-05-28; keyboard nav + paste are first-class acceptance criteria |
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

---

## Phase 2 — Core data model & CRUD ✅

**Started:** 2026-05-28 · **Completed:** 2026-05-28

### Delivered
- Models (all org-scoped, RLS-protected unless noted): `OrgSettings`, `AttritionCurve` (org_id nullable for future global seeds; permissive policy already in place), `Site`, `Trial`, `Arm`, `Visit`, `SiteTrial`, `SiteTrialVisitOverride`.
- Alembic migration `0002_phase2_core_entities.py` — every new table gets the same `org_id::text = current_setting('app.current_org_id', true)` policy shape as the Phase 0 `users` table. `attrition_curves` has the wider `OR org_id IS NULL` clause to support future global seeds. Runtime grants extended to the new tables.
- Signup (`POST /orgs`) now also seeds: one `OrgSettings` row with PRD §5.1 defaults, and three `AttritionCurve` presets (Low 10% / Standard 20% / High 35%), with Standard set as `OrgSettings.default_attrition_curve_id`. This makes a fresh org immediately usable.
- API surface (38 routes total): `/org-settings` (GET, PATCH, admin-only), `/sites` (CRUD, write gated to Org Admin/Ops Lead), `/attrition-curves` (list/POST/PATCH, admin), `/trials` (CRUD + `/activate`), `/trials/:id/arms` and `/arms/:id/visits` (nested CRUD), `/trials/:id/sites` + `/site-trials/:id/visit-overrides` (assignments + overrides).
- Services: `app/services/resolution.py` (PRD §5.2 live-default resolver — site override → visit override → org type default, reading OrgSettings live) and `app/services/trial_activation.py` (draft→active validator with structured failure reasons).
- Validations enforced: `fpfv ≤ lpfv ≤ lplv` on POST and PATCH; `operating_weekdays` subset of {0..6}; `hours_per_day > 0`; `rooms ≥ 1`; `window_days ≥ 0`; `total_dropout_pct ∈ [0,1)`.
- Trial creation auto-creates a "Default Arm" for single-arm trials (`is_multi_arm = False`), so the UI never has to force arm-thinking.

### Gate — automated smoke test ✅

`backend/tests/test_trial_setup_e2e.py` (12 backend tests total, including Phase 0's 4):

```
12 passed in 2.96s
```

Covers:
- Signup auto-seeds OrgSettings + three attrition presets
- Site CRUD + validations (operating_weekdays range, hours > 0)
- Trial date-order validation (`lpfv > lplv` → 422)
- Full happy-path activation: site → trial → arms → visits → site assignment → activate
- Activation correctly rejects: missing randomization visit, missing sites
- **OrgSettings PATCH live-reflows** to the resolution service (the load-bearing assertion for §5.2)
- RLS isolation on Phase 2 tables (Org A's trials/sites invisible to Org B)

Engine: 30/30 tests still green — no regression in the pure forecast layer.

### Gate — manual smoke ✅
- [x] Walked the full trial-setup flow via `curl` against a running backend on 2026-05-28: signup auto-seeded org settings + 3 presets (with Standard as default), site creation worked, trial creation defaulted to Standard attrition, Default Arm auto-created, pre-activation 422 surfaced both `no_visits` + `no_sites` failures together (structured failure list working), adding the 3 visits + assigning the site enabled activation (`draft → active`), PATCH OrgSettings persisted (2.0 → 3.0) without disturbing other defaults. Smoke confirms the e2e test exercises the same path correctly.

### Activation rule (saved as project memory)
`draft → active` requires: ≥1 SoA visit + ≥1 randomization visit + ≥1 active SiteTrial + an attrition curve assigned. Pricing is **not** part of activation (PRD §7.1 separates "volume-ready" from "revenue-ready").

---

## Phase 3 — Projections & actuals 🟡

**Started:** 2026-05-28

### Delivered

**Backend** (`/backend`):
- `EnrollmentWeek` + `EnrollmentWeekHistory` models. Unique on `(site_id, trial_id, arm_id, week_start)`. History is append-only and audits **projection edits only** — actuals overwrite, they don't change a plan.
- Alembic `0003_enrollment_weeks.py` with RLS policies on both tables in the same tenant-isolation pattern as Phase 2.
- Services: `enrollment_audit.diff_projection_fields` (one history row per *changed* projection field per save), `enrollment_variance.compute_trial_variance` (sums per-site projections vs. trial targets, using actuals where past per PRD §5.3).
- API: `GET /site-trials/{id}/enrollment-weeks?from=&to=&arm_id=` (returns rows in range, **zero-projection rows backfilled** so the frontend doesn't have to know the calendar), `PUT /site-trials/{id}/enrollment-weeks` (bulk replace, **past projection edits hard-locked with 409** + structured `offending_week_starts`), `GET /site-trials/{id}/enrollment-weeks/history`, `GET /trials/{id}/variance`. Total routes: 47.

**Frontend** (`/frontend`):
- `SpreadsheetGrid/` — generic headless spreadsheet primitive (built on TanStack Table). Generic over row shape so Phase 4's network grid can reuse it.
  - `useKeyboardNav` — Tab / Shift-Tab / Enter / Shift-Enter / arrow keys, **skipping disabled cells during nav** (the cursor lands on the next *enabled* cell beyond the disabled one).
  - `useClipboardPaste` — TSV parser handles Excel/Numbers/Sheets paste, strips trailing newlines + CRLF, fills a block from the active cell, **skips disabled cells during paste too**, strips thousands commas.
  - `parseTSV` + `parseCellValue` exposed for testing independent of React.
- `hooks/useUnsavedChangesGuard` — Uses React Router 6's `useBlocker` for in-app navigation + `beforeunload` for tab/window close. Fires browser-native confirm only when `dirty === true`. Per the saved feedback memory, every Save-button form must use this.
- `pages/ProjectionGrid.tsx` — Trial+Site pickers, weeks-as-rows grid with Projected/Actual column groups, row classes (`past` → projection cells disabled; `current` → highlighted, both editable; `future` → actuals greyed). Horizontal divider drawn after the current-week row. Variance hint badge above the grid. "View change history" drawer.
- `components/VarianceHint` — Inline "Randomized 87 / goal 100 · 13 under" badges; under-target shown in amber, on/over in emerald. Warn-only, never blocks.
- `components/HistoryDrawer` — Side panel with reverse-chronological audit list.
- Routing: `/projections` added to `App.tsx`; Home page now has a button linking there.

### Gate — automated smoke test ✅

```
backend       19 passed  (12 prior + 7 new Phase 3)
engine        30 passed  (no regression)
frontend      21 passed  (10 paste parser + 11 SpreadsheetGrid behaviors)
```

Backend covers the load-bearing surface:
- Bulk PUT round-trip
- GET pads missing weeks (so the grid renders a complete calendar)
- **Past projection edit → 409 with offending week_start** (the hard-lock assertion)
- Past actual edit succeeds (actuals are the *point* of editing past)
- Audit records only changed projection fields (not unchanged proj, not actuals)
- Variance reports under-target without rejecting (warn-and-allow)
- RLS isolation: Org B cannot read Org A's enrollment weeks or variance

Frontend covers the PRD §7.3 first-class acceptance criteria:
- Tab / Shift-Tab horizontal nav
- Enter / Shift-Enter vertical nav
- Arrow keys in all four directions
- **Disabled cells skipped during keyboard nav** (cursor hops past)
- Stops at grid edge instead of wrapping
- TSV paste fills a 2×3 block from the active cell
- **Disabled cells skipped during paste** (drop the value, keep going)
- Column-group headers render
- Disabled cells render without an input element (can't be typed into)
- `onCellChange` fires on input change
- Divider drawn after the configured row
- Paste parser unit tests for TSV / CRLF / thousands commas / garbage

### Gate — manual smoke ⏳ in progress
- [ ] Bring up backend + frontend dev server, log in, open `/projections`, type into cells with the keyboard, Tab around, Enter down, arrow nav, paste a small block from a spreadsheet, edit a past actual, click Save, refresh and confirm persistence, open the history drawer, attempt to navigate away with unsaved changes (confirm prompt fires)

### Save model + activation rule (saved as feedback memory)
- **Explicit Save button** with dirty-state indicator (button label flips Save ↔ Saved).
- **Unsaved-changes guard** fires on React Router nav + `beforeunload` when dirty. Trial/Site picker dropdowns also confirm before discarding edits.
- Past-projection lock is a **hard 409** at the API; the UI surfaces the offending week_starts inline above the grid.
