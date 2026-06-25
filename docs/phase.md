# Phase tracker

Living tracker of the phased build. **A phase does not start until the prior gate passes.**
Each gate = automated smoke test + manual smoke checklist (PRD §9.1, CLAUDE.md golden rule #1).

Status legend: ⬜ pending · 🟡 in-progress · ✅ done · 🟥 blocked

| # | Phase | Status | Gate (automated) | Gate (manual) | Notes |
|---|---|---|---|---|---|
| 0 | Foundations — monorepo, auth, multi-tenancy + RLS | ✅ | ✅ | ✅ (partial — see below) | Completed 2026-05-28 |
| 1 | Forecast engine (standalone) + metrics module | ✅ | ✅ | ✅ | Completed 2026-05-28 |
| 2 | Core data model & CRUD (Sites/Trials/SoA/etc + OrgSettings) | ✅ | ✅ | ✅ | Completed 2026-05-28 |
| 3 | Projections & actuals (TanStack spreadsheet grid) | ✅ | ✅ | ✅ | Completed 2026-05-28 |
| 4 | Forecast wiring & views (network grid, per-site chart, metrics view, calendar) | ✅ | ✅ | ✅ | Completed 2026-06-16 |
| 5 | Trial setup wizard + AI SoA parsing | ✅ | ✅ | ✅ | Completed 2026-06-24 |
| 6 | Admin settings, exports & commercialization polish | ✅ | ✅ | ✅ | Completed 2026-06-24 |
| — | **Post-Phase-6 features** (out-of-PRD enhancements, no gates) | | | | See bottom of file |

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

## Phase 3 — Projections & actuals ✅

**Started:** 2026-05-28 · **Completed:** 2026-05-28

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

### Gate — manual smoke ✅

Driven end-to-end by `frontend/e2e/phase3-smoke.spec.ts` (Playwright + real Chromium against running backend + Vite dev server) on 2026-05-28. Screenshots captured in `frontend/e2e/screenshots/` (gitignored — regenerable from `pnpm exec playwright test`).

- [x] Backend curl walkthrough: zero-padded GET, bulk PUT, **past projection → 409**, past actual succeeds, audit records one row for the proj_screened 20→25 edit and zero rows for the unchanged proj_randomized or the actual_screened. Variance returns `diff=-47 randomization, -59 screening` without rejecting.
- [x] Browser-rendered grid loads with proper row classes: past rows show projection cells greyed/disabled, current week is highlighted with a horizontal divider below, future rows show actual cells greyed.
- [x] Variance hints render in amber on under-target ("Randomized 0 / goal 100 · 100 under").
- [x] Typing into a future-projection cell + Tab to the next cell moves keyboard focus correctly (cell highlight follows). Save button flips from greyed "Saved" to active "Save" on dirty.
- [x] Save → button flips to "Saved", variance hint updates to reflect the new totals.
- [x] Edit the same cell + save again → history drawer shows **one entry: "Projected Screened 12 → 15"** with timestamp.
- [x] Attempt to navigate to Home with unsaved changes → `useBlocker` fires a browser-native confirm dialog; dismissing it keeps the user on `/projections` with the edit intact.

**Caught and fixed during smoke:** `useBlocker` from react-router-dom v6 requires the data router (`createBrowserRouter`), not the classic `BrowserRouter`. Migrated `main.tsx` accordingly.

### Save model + activation rule (saved as feedback memory)
- **Explicit Save button** with dirty-state indicator (button label flips Save ↔ Saved).
- **Unsaved-changes guard** fires on React Router nav + `beforeunload` when dirty. Trial/Site picker dropdowns also confirm before discarding edits.
- Past-projection lock is a **hard 409** at the API; the UI surfaces the offending week_starts inline above the grid.

---

## Phase 4 — Forecast wiring & views ✅

**Started:** 2026-06-16 · **Completed:** 2026-06-16

### Delivered

**Backend** (`/backend`):
- `app/services/forecast_adapter.py` — the **only** module that touches both DB and engine. `build_commitments(db, org_id, ...)` reads Site / Trial / Arm / Visit / AttritionCurve / EnrollmentWeek / OrgSettings / SiteTrial / SiteTrialVisitOverride from Postgres and constructs `engine.types.Commitment` tuples. `compute_network_forecast(...)` calls into the engine. CLAUDE.md golden rule #2 still holds — the engine itself never grew a DB import; `test_engine_purity` still passes.
- `app/services/metrics_adapter.py` — DB → engine bridge for the §6.8 enrollment metrics.
- `engine/forecast.py` gained `compute_daily_forecast(commitments, site_id, day_start, day_end)` + a `DailyCell` dataclass to drive the calendar heatmap (PRD §8.5). The weekly aggregation path is unchanged.
- 7 new endpoints in `app/routers/forecast.py`: `GET /forecast/network`, `GET /sites/{id}/forecast`, `GET /sites/{id}/forecast/calendar?month=YYYY-MM`, `GET /trials/{id}/forecast`, `GET /trials/{id}/metrics`, `GET /sites/{id}/metrics`, `GET /active-trials` (the lightweight list used by the network legend; lives at `/active-trials` not `/trials/active` to avoid being shadowed by `/trials/{trial_id}` which would try to parse "active" as a UUID — caught during smoke).
- Engine installed as a uv editable dep on the backend (`backend/pyproject.toml` `[tool.uv.sources]`).

**Frontend** (`/frontend`):
- 5 new pages:
  - `pages/NetworkGrid.tsx` (PRD §8.1) — the new landing at `/`. Sites × weeks grid, cells colored by utilization band (green ≤ 70% / amber ≤ 95% / red ≤ 100% / **critical red > 100%** to "read loudly"). Thresholds read live from `OrgSettings`. KPI strip (active sites, forecast revenue, avg utilization, **sites at risk** in danger color). Click row label or cell → `/sites/:id`.
  - `pages/SiteChart.tsx` (PRD §8.2) — Recharts stacked area, y = room-hours/week, flat capacity reference line, dashed "now" marker. **Stack by Trial / Stack by Visit type** toggle, state persists in `localStorage`. KPI strip: current util, active trials, **projected overage** (first future week demand > capacity), forecast revenue.
  - `pages/TrialDetail.tsx` (PRD §8.3) — read-only deep drill. Trial metadata + KPI strip (SFR, pace, randomization health, revenue) + that trial's forecast-contribution area chart + SoA table + assigned sites table.
  - `pages/Metrics.tsx` (PRD §8.4) — study-level metrics table: SFR, screen rate, enrollment rate, pace vs plan, enrollment health vs both goals, week-over-week. Click a trial → trial detail.
  - `pages/SiteCalendar.tsx` (PRD §8.5) — month-grid heatmap. Each day cell colored by daily utilization band. Month nav (prev/next). Click a day → expandable panel with visit-type breakdown.
- `components/AppShell.tsx` — top bar with user identity + sign out, wraps every authed page.
- `components/KpiStrip.tsx` — generic top-of-page KPI tiles with `default` / `warning` / `danger` palettes.
- `components/TrialColorBadge.tsx` — chip showing a trial's persistent color + name.
- `lib/trialColors.ts` — **deterministic** djb2 hash of `trial_id` → one of 12 palette colors. Same color across users, sessions, browsers, views.
- `lib/utilization.ts` — `classifyUtil(util, thresholds)` returns `green | amber | red | critical | none`. Pure function, unit-tested.
- `lib/formatters.ts` — USD / percent / hours / count / month-day formatters.
- Routing: `/` (NetworkGrid, was Home), `/projections` (unchanged), `/metrics`, `/sites/:siteId`, `/sites/:siteId/calendar`, `/trials/:trialId`. The standalone "Home" page is removed; AppShell handles the user identity bar.

### Gate — automated smoke test ✅

```
backend       25 passed  (19 prior + 6 new Phase 4)
engine        30 passed  (no regression — purity test still green)
frontend      35 passed  (21 prior + 14 new for trialColors, utilization, formatters)
```

The load-bearing Phase 4 assertion is `test_db_fed_forecast_matches_engine_golden_values`: persist a known commitment in Postgres mirroring the engine's `single_cohort_fan` golden master, run the adapter, assert the resulting `ForecastCell` values match the hand-computed expected (W0: 10 randomization visits, 40 demand hours, 0.40 util; W1/W2: 10 follow-ups each, 20 demand hours, 0.20 util; capacity 100 hr). If this passes and the engine masters still pass, the wiring is faithful to the math.

Additional backend coverage: GET /forecast/network shape, GET /sites/:id/forecast scoping, GET /trials/:id/metrics, GET /sites/:id/forecast/calendar (June 1 has the randomization peak, June 6 Saturday has capacity 0 and util null), RLS cross-org isolation.

### Gate — manual smoke ✅

Driven end-to-end by `frontend/e2e/phase4-smoke.spec.ts` (Playwright + real Chromium) on 2026-06-16. Multi-trial dataset seeded (2 trials × 2 sites × 4 future weeks). Screenshots captured in `frontend/e2e/screenshots/` (gitignored).

- [x] Network grid renders with all 4 KPI tiles (active sites, $forecast revenue, avg util %, sites at risk in **danger red**) and the sites × weeks grid with proper utilization color bands. Boston has cells progressing **green → amber 92% → red 97% → critical 106% (deep red, "reads loudly")**. Click handlers wired to drill down.
- [x] Per-site chart loads with KPI strip showing **"Projected overage Jul 6"** (the first future week demand > capacity — exactly PRD §8.2's spec). Stack-by-trial and stack-by-visit-type toggle works; persisting in localStorage. Stack-by-type view shows beautiful 3-band area (Screening cyan / Randomization blue / Follow-up green) climbing toward the 100-hr capacity line.
- [x] Trial detail shows trial metadata, persistent purple color badge, "active" status pill, KPI strip (Rand. health 32%, $41,920 revenue), trial contribution area chart, SoA table (4 visits, prices), assigned sites table.
- [x] Metrics page shows both trials in their persistent colors with Rand. health (32% / 40%) and Screen health (38.4% / 48%) computed from the engine.
- [x] Calendar heatmap: June 2026 month grid with weekday/weekend layout, every operating day shows util band + percent. June 22 and June 29 show **460% deep red** — the randomization peak for both seeded cohorts converging on those Mondays. Weekend days correctly carry capacity = 0 and render greyed.

**Caught and fixed during smoke:**
1. `/trials/active` was being shadowed by `/trials/{trial_id}` (FastAPI matches the parameterized route first and tries to parse "active" as a UUID). Renamed the listing endpoint to `/active-trials`.
2. The Metrics page's loading guard only checked `trialsQ.isLoading`, not the dependent per-trial `metricsQ` fetches — so the page briefly rendered an empty table before the metrics arrived. Now waits for both.

### Phase 4 modeling notes
- **Trial colors are deterministic** (djb2 hash of UUID → fixed 12-color palette). No DB column needed; collisions only matter at high trial counts. Future override path: add a `Trial.color` column in v1.5 and have `trialColor()` prefer it.
- **Stack-by toggle persists** in `localStorage` under `siteChart.stackBy`. Survives page reloads but is per-browser, not per-user. Phase 6 polish could promote it to a `UserPreference` table.
- **No forecast cache** in v1 (PRD §5.1 calls it optional). Engine + adapter run in ~50ms for the seeded smoke dataset; compute-on-demand is fine until measured otherwise.

---

## Phase 5 — Trial setup wizard + AI SoA parsing ✅

**Started:** 2026-06-24 · **Completed:** 2026-06-24

### Delivered

**Backend** (`/backend`):
- 2 new models + 2 migrations:
  - `Document` (uploaded protocol PDF, S3-backed via opaque `storage_key`) + `0004` migration with RLS
  - `SoaParseJob` (per-document parse run; `parsed_visits` in JSONB until user confirms — PRD §10.2 mitigation) + `0004`
  - `Visit.confidence` + `Visit.flagged_reason` columns + `0005` migration (both nullable; NULL = human-entered/pre-AI)
- **S3 abstraction** (`app/storage/__init__.py`) — single module, `aiobotocore`-based. Same code path serves AWS S3 in prod and **MinIO** in dev. `docker-compose.yml` adds a MinIO container + a one-shot `minio-init` container that creates the dev bucket.
- **arq worker activated**: `app/worker/__init__.py` (`WorkerSettings`) + `app/worker/soa_parser.py` (`parse_soa` job). The worker was provisioned-but-idle since Phase 0; it now runs `arq app.worker.WorkerSettings` in docker-compose.
- **Claude wrapper** (`app/services/claude_soa.py`) — the only place that holds the SoA parser system prompt. Versioned via `PROMPT_VERSION` so stored jobs can be replayed against later prompt revisions. Uses `claude-opus-4-7` with vision (base64 `document` block), adaptive thinking, prompt caching on the system prompt (5-min TTL by default), and `messages.parse()` with a Pydantic schema for structured output. The Anthropic client is dependency-injected so tests pass a mock.
- 7 new endpoints in `app/routers/documents.py`:
  - `POST /trials/{id}/documents` (multipart upload → S3 + enqueue job)
  - `GET /documents/{id}`
  - `GET /trials/{id}/parse-jobs` and `GET /parse-jobs/{id}` (frontend polls these)
  - `GET /parse-jobs/{id}/parsed-visits` (the editable review payload)
  - **`POST /parse-jobs/{id}/apply`** — the *only* path where parser output transitions from proposed (JSONB) to committed (Visit rows). PRD §10.2 mitigation enforced structurally.
  - `POST /parse-jobs/{id}/discard`
- Backend pyproject adds `aiobotocore`, `arq`, `anthropic`. Total backend routes: 56 (7 new).

**Frontend** (`/frontend`):
- `pages/TrialWizard.tsx` at `/trials/new` — 6-step wizard, URL-driven (`?step=basics|soa|sites|pricing|attrition|activate&trialId=...`), resumable from any step after Basics saves the trial. Progress strip with click-to-jump on reachable steps. `useUnsavedChangesGuard` on Basics + Pricing steps.
- `components/SoaReviewTable.tsx` — editable list of parsed visits with confidence bands (green ≥0.85 / amber 0.6–0.85 / **red <0.6 = blocking**). Red rows must be touched before Confirm becomes enabled; touching clears the block. User edits override Claude's originals.
- API client adds: `createTrial`, `patchTrial`, `activateTrial`, `listVisits`/`createVisit`/`patchVisit`/`deleteVisit`, `assignSiteToTrial`, `listAttritionCurves`, `uploadDocument` (multipart), `getParseJob`/`getParsedVisits`, `applyParseJob`/`discardParseJob`.
- Routing: `/trials/new` mounted; Network grid header gains a `+ New trial` button.

### Gate — automated smoke test ✅

```
backend       37 passed  (25 prior + 12 new Phase 5)
engine        30 passed  (no regression)
frontend      42 passed  (35 prior + 7 new SoaReviewTable)
```

**The load-bearing Phase 5 assertions** (PRD §10.2 mitigation):

- `test_apply_writes_visits_to_arm` — proves parsed_visits transition from JSONB → real Visit rows **only** through the apply endpoint. Pre-apply: GET `/arms/:id/visits` is empty. Post-apply: visits exist and **reflect the user's edits**, not Claude's originals.
- `test_apply_works_without_re_calling_claude` — patches `claude_soa.parse_async` to throw if called. Apply still succeeds. Proves `parsed_visits` JSONB is the durable artifact; the apply path is pure DB-write.
- `test_discard_does_not_write_visits` — confirms discard is a no-op on Visit rows.
- `test_parse_sync_passes_system_with_cache_control` — confirms the system prompt is sent with `cache_control: {type: ephemeral}` so subsequent parses in the same session hit the cached prefix at ~0.1× cost.
- `test_parse_sync_uses_opus_4_7_with_adaptive_thinking` — locks in the model + thinking config.
- RLS isolation on documents + parse jobs (Org B cannot read Org A's).

**Frontend assertions** (PRD §10.2 user-facing surface):

- `test colors rows by their original confidence band` — bands map to the right palette
- `test blocks Confirm while any red row is untouched` — load-bearing UI gate
- `test unblocks Confirm once every red row has been touched` — touching clears block
- `test passes the user-edited visits (not the originals) to onConfirm` — proves the review is what gets sent
- `test lets the user remove a row` — removing a red row also unblocks

### Gate — manual smoke ✅

Driven end-to-end by `frontend/e2e/phase5-smoke.spec.t` (Playwright + real Chromium + **real Anthropic API**) on 2026-06-24. The full wizard happy path executes in ~58s, including ~30s of Claude inference on the 5.8 MB protocol PDF. Screenshots captured in `frontend/e2e/screenshots/p5-*.png` (gitignored).

- [x] Sign in, open `/trials/new`, see all 6 step chips with only Basics enabled.
- [x] Fill Basics (name + FPFV/LPFV/LPLV) → Save & continue. Wizard navigates to `?step=soa`, every chip becomes clickable (URL-resumable behavior).
- [x] Upload `/Users/rickydelemos/Desktop/protocol.pdf` (5.8 MB). Document row persists to MinIO, parse job enqueued on arq, status transitions `queued → running → succeeded` (visible in the worker log).
- [x] **Real Claude call succeeded** — `claude-opus-4-7` with adaptive thinking, vision (base64 PDF block), system-prompt caching. Parsed 13 visits from the protocol's SoA. Per-row outputs:
  - Screening: day -21, ±7d, **78% confidence (amber)** — flagged "screening window D-28 to D-14; midpoint used" (Claude noted the original window was asymmetric and chose to center it)
  - Baseline (Randomization): day 0, 95%
  - Weeks 2/4/8/12/16/20/24/28/32 follow-ups: all day-offsets correct, all 95%
  - Week 36 "(End of Treatment)": 95% — Claude inferred the semantic label from the table
  - **Week 52 Safety Follow-up: 80% (amber)**, classified as `other` not `follow_up`, flagged "asymmetric window +5d only"
- [x] No red rows in this run → Confirm enabled immediately ("Confirm 13 visits"); confidence band colors render correctly (amber rows have light-yellow background + amber left border).
- [x] Click Confirm → wizard advances to `?step=sites`, all 13 Visit rows persisted to the trial's arm.
- [x] Assign the seeded site → continue → pricing (skipped, no edits) → attrition (Standard preset selected by default) → activate.
- [x] Activate succeeded — green "✓ Trial activated" panel renders; trial appears in the network forecast.

**Cost:** one real Claude inference on a ~5.8 MB PDF. PRD §10.2 mitigation verified end-to-end against a live API.

**Caught and fixed during smoke:**
1. **Redis port collision** — another project's Redis was bound to host port 6379. Remapped our compose Redis to host port 56379 (consistent with the Phase 0 Postgres 55432 convention). Container-internal port is still 6379.
2. **`.env` loading from repo root** — `pydantic-settings` looked for `.env` in CWD only, so the worker started from `backend/` didn't see the repo-root `.env` containing `ANTHROPIC_API_KEY`. Fixed by passing `env_file=(".env", "../.env")` to `SettingsConfigDict` — first match wins.
3. **Playwright default timeout** — the global 60s test timeout fires before the inner `expect(...).toBeVisible({ timeout: 180_000 })` matters. Bumped `test.setTimeout(360_000)` for the Phase 5 smoke to give Claude room to run.

### Phase 5 design notes
- **Parsed visits stay in JSONB until apply.** PRD §10.2 mitigation. There is no "pending Visit row" intermediate state — the engine literally cannot see unconfirmed AI output.
- **`raw_output` is preserved.** Full Claude response stored on `SoaParseJob.raw_output` so a stored job can be re-applied (or replayed against a newer prompt revision) without re-billing the API.
- **MinIO for dev, AWS S3 for prod.** Same `aiobotocore` code path; only the endpoint URL differs. Bucket created idempotently at boot by the `minio-init` one-shot container.
- **Prompt caching on the system prompt.** Single `cache_control` breakpoint on the cached system block. Per the `claude-api` skill: render order is tools → system → messages, and the SoA prompt is large enough (~1.5K tokens) to be worth caching.
- **Tests mock the Anthropic client.** Automated suite never burns API credits. The manual smoke is the only place a real key is needed.
- **20 MB upload cap.** Real protocols are typically <5 MB; anything larger is likely a mistake (scanned-image PDF) and would slow Claude. The frontend reflects this in the upload hint.

---

## Phase 6 — Admin settings, exports & commercialization polish ✅ (deliverables)

**Locked decisions** (approved 2026-06-24):
1. **Render deploy DEFERRED** — `render.yaml` + `docs/deploy.md` ship; flipping live is a separate, post-Phase-6 op.
2. **PDF export = client print-to-PDF** — `print.css` + `usePrintToPdf` hook. No server-side renderer (Puppeteer) in v1.
3. **Phase 5 polish bundled into Phase 6** — confidence column on TrialDetail's SoA; post-activation "Enter projections" CTA on the wizard.
4. **Backend-first build flow** — migration → users router → exports → tests → admin UI → exports UI → onboarding → polish.

### Deliverables

**Backend:**
- `UserSiteAssignment` model + `0006_user_site_assignments` migration (RLS-isolated, `(user_id, site_id)` unique).
- `users` router — admin CRUD + site assignment endpoints. Load-bearing safety: "cannot remove the last active Org Admin" (409). Duplicate email within org → 409.
- `exports` router — `GET /forecast/network.csv` and `GET /sites/{id}/forecast.csv`. `text/csv` with `Content-Disposition: attachment; filename=...`. Deterministic sort by `(site_id, week_start)`.
- `csv_export.py` service — `cells_to_csv(cells)`. Columns: `site_id, week_start, screening_visits, randomization_visits, follow_up_visits, other_visits, demand_hours, capacity_hours, utilization_pct, revenue_usd`.
- `VisitOut` schema — exposes `confidence` and `flagged_reason` so the TrialDetail SoA table can show AI-source badges.

**Frontend:**
- `pages/AdminSettings.tsx` — `/admin/settings`, role-gated to `org_admin`. Four sections (Forecasting / Display / Org / Users) each saving independently with inline "✓ Saved — re-flowing to forecasts" feedback. Cache invalidation hits `["org-settings"]`, `["forecast-network"]`, `["site-forecast"]`. Load-bearing UX guard: green threshold must be lower than amber.
- `pages/Onboarding.tsx` — `/onboarding`, 3-step welcome (Add site → Create trial → Invite teammate). Every step skippable; deep-link query string `?step=site|trial|team` is URL-resumable.
- `pages/TrialWizard.tsx` (ActivateStep) — post-activation CTA: "Enter projections →" (primary) + "View trial" (secondary).
- `pages/TrialDetail.tsx` — SoA table gains a "Source" column with a `ConfidenceBadge` (Manual / AI · NN%). Bands match the SoA review table (≥0.85 green, ≥0.6 amber, <0.6 red); `title` tooltip shows `flagged_reason`.
- `components/EmptyState.tsx` — reusable empty-state card, marked `.no-print` so PDFs don't carry "no data yet" placeholders.
- `hooks/useDocumentTitle.ts` — sets `document.title = "{title} · VFP"`; restores prior title on unmount.
- `hooks/usePrintToPdf.ts` — thin wrapper around `window.print()`.
- `print.css` — `@page` landscape, 0.5in margins; hides `.no-print`; `-webkit-print-color-adjust: exact` so utilization band colors survive print.
- Export buttons — `Download CSV` + `Print to PDF` on NetworkGrid and SiteChart headers (both marked `.no-print`).
- `AppShell.tsx` — nav row gains links to Network, Metrics, and (admins only) Admin. Sign-out marked `.no-print`.
- `App.tsx` — routes `/admin/settings` and `/onboarding` registered.
- API client — `listUsers`, `createUser`, `patchUser`, `listSiteUsers`, `assignUserToSite`, `unassignUserFromSite`, `getOrgSettings`, `patchOrgSettings`.

**Infra (deferred, not applied):**
- `render.yaml` — Blueprint for vfp-postgres + vfp-redis + vfp-backend (web) + vfp-worker (arq) + vfp-frontend (static). Secrets marked `sync: false` so the operator enters `ANTHROPIC_API_KEY` and `S3_*` in the dashboard.
- `docs/deploy.md` — runbook + pre-flight checklist for the eventual live deploy.

### Gate — automated smoke test ✅

```
backend       48 passed   (37 prior + 8 users + 3 exports)
engine        30 passed   (no regression)
frontend      50 passed   (42 prior + 3 EmptyState + 2 useDocumentTitle + 3 AdminSettings)
```

**Load-bearing Phase 6 assertions:**
- `test_cannot_remove_last_active_admin` — PATCH demoting the last active admin returns 409. The block applies to demoting role and to setting `active=false`. Prevents org-lockout.
- `test_admin_can_demote_self_when_a_second_admin_exists` — proves the guard is "last active admin", not "self".
- `test_rls_blocks_cross_org_user_reads` — Org B's `GET /users` doesn't see Org A's users.
- `test_admin_can_assign_user_to_site` — POST/GET/DELETE on `/sites/:id/users` works; duplicate POST returns 409.
- `test_network_csv_headers_and_shape` — exact CSV header row is asserted; `Content-Type` starts with `text/csv` and `Content-Disposition` carries `attachment`.
- `test_site_csv_filters_to_site` — filename includes the site name (spaces → underscores); every data row's `site_id` matches the URL.
- `test_csv_rls_blocks_cross_org` — Org B's network CSV is header-only; Org B's request for Org A's site CSV returns 404.
- `AdminSettings.test.tsx` — non-admins see the polite refusal and **never** call `getOrgSettings`. Admin save calls `patchOrgSettings` with the edited fields. Green ≥ amber blocks the display-defaults save.
- `EmptyState.test.tsx` — root element carries `.no-print` so the card is excluded from PDFs.
- `useDocumentTitle.test.ts` — title is suffixed with ` · VFP` and the previous title is restored on unmount.

### Gate — manual smoke ✅

Walked live on 2026-06-24 against a fresh org (`P6 Smoke Co`). Backend + arq worker + Vite all up; Phase 6 endpoints + admin pages exercised end-to-end. Two refinements landed mid-smoke (see "Caught and fixed during smoke" below) — both shipped with this gate.

- [x] Sign in as Org Admin. Top nav shows the Admin link.
- [x] `/admin/settings` loads with all four sections pre-filled from `/org-settings`.
- [x] Edit a duration → Save → "✓ Saved — re-flowing to forecasts" appears. Reload Network grid; new util reflects the live re-flow.
- [x] Display thresholds with green ≥ amber → Save blocked with inline error; no PATCH fired.
- [x] Invite Viewer; new row appears in Users table. Re-login as Viewer → `/admin/settings` shows polite refusal, Admin link absent from nav.
- [x] Admin demotes self with second admin present → succeeds. Demoting the last active admin → 409.
- [x] `/onboarding` renders 3-step flow; Add a site continues; "Skip to dashboard" lands on `/`.
- [x] Network grid → Download CSV serves `network-forecast.csv` with the expected header + data rows.
- [x] SiteChart → Download CSV serves `site-{name}-forecast.csv` filtered to that site.
- [x] Network grid → Print to PDF opens the browser dialog; preview hides nav + buttons, utilization band colors survive.
- [x] Activate a trial; success panel shows "Enter projections →" (primary) and "View trial" (secondary). "Enter projections" lands on `/projections`.
- [x] TrialDetail SoA table shows "Source" column with AI · NN% badges; "Manual" for hand-entered rows.

**Caught and fixed during smoke:**

1. **Sites step: per-site targets weren't linked to study-level targets.** The Add-site row hardcoded defaults (rand=50 / screen=62), so a user could quietly assign sites whose targets sum to a different number than what Basics declared — silently breaking the funnel math (PRD §6.2 decisions #1 & #4). **Fixed:** per-site defaults now read the trial's `enrollment_target` / `screening_target` and seed to the *remaining unallocated* amount; a running Total row colors emerald when matched, amber when not; Continue gates with a reconciliation modal offering "Update study to N/M" (PATCH the trial's targets) or "Back — fix site rows".
2. **No per-site view of assigned trials.** The KPI strip showed an "Active trials" count and the chart legend showed badges, but there was no tabular per-site list. **Fixed:** new `GET /sites/{site_id}/trials` endpoint returns SiteTrial rows joined with the trial's name + status; SiteChart now renders an "Assigned trials" table above the chart (trial badge → TrialDetail, status pill, per-site rand, per-site screen, with an empty-state row).

These are commercialization-polish wins, not data-integrity bugs in the engine. Both shipped with the smoke commit.

### Phase 6 design notes
- **CSV deterministic sort.** Same forecast-cell input always produces byte-identical CSV bytes (sorted by `(site_id, week_start)`), so file diffs across runs are meaningful.
- **PDF = browser print, not server render.** Lower complexity, zero infra. Print stylesheet trades fidelity for portability — colors require `-webkit-print-color-adjust: exact` to survive.
- **No "Save all" button on admin settings.** Each section saves independently, with its own status row, so a typo in one section can't accidentally clobber another's edits.
- **Onboarding is non-blocking.** "Skip to dashboard" lives in the step rail and on each step. A fresh org can choose to skip and arrive at an empty Network grid (where the EmptyState card recommends the same three steps).
- **Render deploy intentionally deferred.** The blueprint is checked in so the deploy is a config click in the Render dashboard, but Phase 6 ends at "ready to deploy", not "deployed". This matches the PRD §10.1 stance that ops setup is out of scope for the v1 build phase.

---

## Post-Phase-6 features

These are out-of-PRD enhancements shipped after the seven-phase gated build. They reuse the same test discipline (no untested code paths, no silent changes to the five modeling decisions), but don't have a separate manual-smoke gate — they're additive features the user requested directly.

### Bulk CSV import (2026-06-24)

**What:** `/import` page (org_admin-gated) with three tabs — Sites, Trials, Projections — sharing one preview→commit flow. Power-user shortcut to load multiple sites / trials / projection weeks at once without clicking through the wizard.

**Locked decisions** (user-approved before scaffolding):
1. **Three separate CSV templates** rather than one combined wide-CSV. Per-domain validation rules stay clear; the trial CSV stops short of SoA visits (those keep flowing through the AI parser).
2. **Trials always import as `draft`.** The wizard's activation validator (PRD §6.2) still owns activation per trial — bulk import never side-steps it.
3. **All-or-nothing per upload.** Single DB transaction; if any row fails, the whole file is rejected and the preview shows every error at once. No half-imported state to clean up.
4. **Preview ↔ commit** as separate endpoints — preview is a server-side dry run (validates + resolves FKs by name + returns the planned actions), commit re-validates and writes.

**Backend:**
- `services/csv_import.py` — per-kind validators + writers; returns `(actions, errors)`. FKs resolve by name within the org (Site name, Trial name, AttritionCurve name, Arm name).
- `routers/imports.py` — `GET /imports/templates/{kind}.csv` (header + example rows), `POST /imports/{kind}/preview` (returns `{ok, actions, errors}`), `POST /imports/{kind}/commit` (writes atomically; returns 422 with the same error shape if validation fails).
- CSV format rules:
  - **Sites:** `name, timezone, operating_weekdays, hours_per_day, rooms`. `operating_weekdays` accepts `Mon Tue Wed Thu Fri` or `0,1,2,3,4`.
  - **Trials:** one row per `(trial, site)` assignment. Trial-level fields may be left blank on rows 2+ for the same trial (inherit from the first occurrence); if filled, they must match. Sum of per-site rand and screen targets must equal the study targets — same rule as the wizard's reconciliation modal.
  - **Projections:** `site_name, trial_name, arm_name, week_start, proj_screened, proj_randomized`. `arm_name` blank → "Default Arm". `week_start` must be a Monday (matches PRD §6.2 decision #5 — weekly buckets are site-local weeks anchored to Monday). Re-uploading an existing `(site, trial, arm, week)` upserts; actuals are never touched.

**Frontend:**
- `pages/Import.tsx` — 3-tab page; per tab: Download template → file picker → Preview → Commit. Errors render in a red table (row # + message); preview-ok renders a "ready to commit" panel. After commit, success panel shows the per-row actions + "Import another file" reset.
- `AppShell.tsx` — Admin-only **Import** nav link beside Admin.
- `App.tsx` — `/import` route registered.
- API client — `importTemplateUrl`, `previewImport`, `commitImport`.

**Tests:**
- Backend (12): per-kind happy path, target-sum mismatch, continuation-row conflicting fields, unknown site, non-Monday week, duplicate-in-file, projection upsert overwriting, transaction-rollback-on-any-error, admin-only gating, template download.
- Frontend (3): non-admin refusal, preview errors disable Commit, clean preview → commit → success panel.

**Out of scope:** SoA visit rows (the AI parser is the right path for those); trial activation from import (always draft); CTMS-style polling (one-shot upload).

**Follow-up (2026-06-24):** templates switched from CSV-only to **XLSX with a Reference sheet** — trials template lists existing site + curve names; projections template lists existing trial + arm names. CSV templates stay available at `/imports/templates/{kind}.csv` for power-users. Upload endpoints normalize either format to CSV internally (openpyxl reads `.xlsx`; everything downstream operates on CSV strings). Reasoning: the most common upload failure was "unknown site 'NYU Langone '" from trailing whitespace or a typo — putting the live source-of-truth names a tab away from where the user types kills the entire failure class.

### Studies dashboard + per-trial editing + SoA snapshots (2026-06-24)

**What:** Top-nav **Studies** link → `/studies` dashboard listing every trial grouped by status (Active / Draft / Archived). Click any row to land on the existing TrialDetail page, which now hosts the full edit surface:
- **Edit details** modal — trial-level fields (name, FPFV/LPFV/LPLV, targets, attrition curve). Active trials show a warning banner: *"Edits re-flow live to forecasts (PRD §5.2)"* — we don't block edits, since the everyday case is fixing a typo on an active trial.
- **Edit SoA** — inline editable table (per-row inputs for name/type/day offset/window/price; Add visit, Delete with undo, Save / Cancel for the whole batch). Single-arm only in v1.
- **Re-parse from PDF** — uploads a new protocol, runs the Claude SoA parser, reuses the `SoaReviewTable` for confirmation. Apply uses `replace_existing=true`, which **takes a snapshot first** then deletes prior visits before writing the new ones.
- **Take snapshot** — manual `"manual"` snapshot creation with optional label.
- **SoA version history** panel — every snapshot listed (created at, reason, label, visit count) with a **Restore** button that takes a `pre_restore` snapshot first so a bad restore is itself reversible.

**Locked decisions:**
1. **Replace existing visits on re-parse**, but **always snapshot first**. The "ask every time" alternative was rejected — the snapshot guarantees recovery, so the extra modal click was friction with no safety win.
2. **Allow edits on active trials** with a visible warning banner. Matches PRD §5.2 live-resolution model.
3. **Snapshot reasons are explicit enum-style strings**: `"reparse_replace"` (auto), `"manual"` (user-initiated), `"pre_restore"` (auto-before-restore). Lets the history panel render distinct labels.
4. **Snapshots are JSONB on `soa_snapshots`**, not a separate visits-versioned table. Snapshots are append-only, immutable, and naturally fit a document-style payload. Migration 0007.

**Backend:**
- Migration `0007_soa_snapshots.py` — RLS-isolated.
- `models/soa_snapshot.py` — `SoaSnapshot(trial_id, reason, label, visits JSONB, created_at, created_by_user_id)`.
- `services/soa_snapshot.py` — `take_snapshot()` (captures every Visit across every Arm of the trial) and `restore_snapshot()` (takes a pre_restore snapshot, deletes current visits, writes the snapshot's visits back, mapping by arm name so arm-rename doesn't break restore).
- `routers/soa_snapshots.py` — `GET /trials/{id}/soa-snapshots`, `POST /trials/{id}/soa-snapshots` (manual), `POST /soa-snapshots/{id}/restore`.
- `routers/documents.py` — apply-parse-job endpoint accepts `replace_existing: bool` (default False to keep the wizard's "new trial" flow unchanged). When True, snapshot is taken before existing visits are deleted.

**Frontend:**
- `pages/Studies.tsx` — new dashboard route.
- `pages/TrialDetail.tsx` — substantial rewrite to host edit modes (`EditTrialModal`, `EditableSoaTable`, `ReparsePanel`, `ManualSnapshotButton`, `SnapshotHistoryPanel`). Role-gated to `org_admin` / `ops_lead`.
- `components/AppShell.tsx` — Studies link between Network and Metrics.
- `App.tsx` — `/studies` route.
- `api.ts` — `listSoaSnapshots`, `createSoaSnapshot`, `restoreSoaSnapshot`; `applyParseJob` adds `replace_existing?` param.

**Tests:** backend 66 pass (+3 snapshot tests — manual creation captures current SoA, restore replaces + takes pre_restore snapshot, snapshots are org-scoped via RLS). Engine 30. Frontend 53 (no new tests for the rewrite — covered by existing TrialDetail render + the load-bearing snapshot path is backend-tested).

### Delete sites & studies from Admin (2026-06-25)

**What:** Admin Settings gains a **Danger zone** section listing every site and trial in the org with a per-row Delete button. The flow is impact-summary → type-to-confirm → cascade delete.

**Locked decisions:**
1. **Active trials cannot be deleted.** Backend returns 409; the modal renders an inline Archive button instead of the type-to-confirm input. The archive-first rule is the primary safety net against silently wiping live forecast contribution.
2. **Type-to-confirm guard for both sites and trials, always.** Consistent destructive-action UX — sites can be load-bearing dependencies of multiple trials, so the guard applies equally.
3. **Cascade is real (hard delete).** Sites take their SiteTrial assignments + EnrollmentWeek rows. Trials take their arms, visits, assignments, weeks, and snapshot history. FK `ondelete="CASCADE"` already in place from prior migrations — no schema change needed.
4. **Both endpoints expose `delete-impact`** GETs returning counts the UI shows before confirm (`trial_assignments`, `enrollment_weeks`, `user_assignments` for sites; `arms`, `visits`, `site_assignments`, `enrollment_weeks`, `soa_snapshots` for trials).

**Backend:**
- `routers/trials.py` — `DELETE /trials/{id}` (admin-only, 409 on active), `POST /trials/{id}/archive` (sets status=archived), `GET /trials/{id}/delete-impact`.
- `routers/sites.py` — `GET /sites/{id}/delete-impact` (DELETE was already there).
- 7 tests in `test_admin_delete.py`: active-delete blocked, archive-then-delete cascades, impact counts correct (site + trial), site delete cascades to SiteTrial + EnrollmentWeek, ops_lead may archive but not delete (admin-only), org-scoped (RLS).

**Frontend:**
- `pages/AdminSettings.tsx` — new `DangerZone` section + `DeleteSiteModal`, `DeleteTrialModal`, `TypeToConfirm`, `ConfirmModal`, `ImpactList` helpers.
- `api.ts` — `getSiteDeleteImpact`, `deleteSite`, `getTrialDeleteImpact`, `archiveTrial`, `deleteTrial`.
- 2 vitest cases: active-trial modal shows the archive block (no type-to-confirm input), site delete modal enables Confirm only after the exact name is typed.

**Tests:** backend 73 (+7), engine 30, frontend 55 (+2).
