# Clinical Clarity — Product Requirements Document (v1)

> **Status:** Ready for implementation
> **Audience:** Claude Code (implementer) and the product owner
> **Format note:** This document is opinionated. Where a topic was decided, it states a single decision rather than options. Where a default was chosen without explicit sign-off, it is marked `[default — overridable]`.

---

## 1. Overview & Problem Statement

### 1.1 The business
The customer operates a **network of clinical trial sites**. Each site runs multiple trials simultaneously; some trials run across multiple sites, but each site has its own mix. Trials follow protocol-defined **Schedules of Activities (SoA)** — visits at set day-offsets from randomization, each within a timing window.

### 1.2 The problem
There is no structured, forward-looking view of **site visit volume vs. site capacity**. The customer cannot reliably answer the core operational question:

> **"Should I sell this location into another trial, or am I about to break it?"**

Today this is pieced together manually from spreadsheets. The decision is made **weekly**, by the executive, with site managers needing visibility into their own locations.

### 1.3 The solution
A multi-tenant SaaS application that forecasts weekly visit volume per site by combining enrollment projections, the protocol SoA, and attrition; compares that demand against site capacity (measured in room-hours); and derives a revenue forecast from per-visit pricing. **v1 is read-only forecasting. v2 adds what-if simulation.**

### 1.4 The strategic edge
Unlike generic capacity-planning tools that must guess at demand, this product has a **deterministic backbone**: once a patient is randomized, the protocol dictates exactly which visits they generate and when. The forecast is a stochastic build-up from deterministic building blocks.

---

## 2. Goals & Success Criteria

v1 is successful when:

1. **Decision confidence.** The executive opens the app weekly and gets an unambiguous read on where capacity is at risk and where there is room to sell, without assembling spreadsheets.
2. **Trust in the numbers.** The near-term forecast lands within ~10–15% of actuals, trustworthy enough to base commitments on. The app surfaces projected-vs-actual variance over time so trust is demonstrable, not asserted.
3. **Commercialization readiness.** By end of v1, the product can be demoed to another trial network with a plausible path to selling them a tenant — meaning real multi-tenancy, a working new-org onboarding flow, and a non-prototype polish bar.

**Derived requirement (not on the customer's explicit list but a prerequisite to #2):** site-manager adoption. Trust in the numbers requires actuals; actuals require site managers to enter them; therefore projection/actuals entry UX must be genuinely good (see §7.3).

---

## 3. Personas & Roles

Single product, **same screens for everyone, scoped by data access**. A user only sees the sites they have permission to see.

| Role | Scope | Capabilities |
|---|---|---|
| **Org Admin** (Executive) | All sites in org | Everything + user management + trial setup |
| **Ops Lead** | All sites in org | View all; create/edit trials; enter/edit projections & actuals. No user management. |
| **Site Manager** | Assigned site(s), one or many | View own sites; enter/edit projections & actuals for own sites. |
| **Viewer** | Assigned site(s) | Read-only. |

- **Multi-tenancy:** full org-level isolation. No cross-org access.
- **No trial-level permissions** — scoping is site-level only.
- A single user may manage multiple sites.

---

## 4. Tech Stack & Architecture

### 4.1 Architectural keystone
**The forecast engine is a standalone, pure-Python package with zero web/DB/HTTP dependencies.** It accepts a set of *commitments* (trials, SoAs, projections, actuals, attrition curves, capacity params) and returns a forecast. This makes it (a) exhaustively unit-testable via golden-master tests — the basis for trusting the math — and (b) directly reusable for v2 simulation, which simply feeds it hypothetical commitments. Everything else is plumbing around this core.

### 4.2 Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic |
| Forecast engine | Pure Python (numpy/pandas), standalone package `engine/` |
| Database | PostgreSQL — shared-schema multi-tenancy (`org_id` on every table) + Row-Level Security |
| Frontend | React + TypeScript + Vite + Tailwind + TanStack Query + TanStack Table + Recharts |
| Auth | Cookie-based sessions, Argon2 password hashing; module designed for future SSO |
| AI SoA parsing | Anthropic Claude API (vision) → structured visit JSON; runs as background task |
| Async jobs | Arq + Redis |
| Packaging | Docker + Docker Compose; monorepo |
| Hosting | Render: FastAPI web service + static React site + managed Postgres + Redis + Arq worker |

### 4.3 Repo layout
```
/engine      pure-Python forecast engine + golden-master tests (no web/db deps)
/backend     FastAPI app, SQLAlchemy models, Alembic migrations, API routes, auth
/frontend    React + TS app
/docs        prd.md (this file), phase.md, architecture.md
docker-compose.yml
```

### 4.4 Multi-tenancy
Shared schema; every table carries `org_id`. Tenant isolation enforced at the query layer **and** by Postgres Row-Level Security as defense-in-depth. No schema-per-tenant or db-per-tenant in v1.

### 4.5 Internationalization posture
- **Currency:** USD only in v1, but money fields carry an explicit currency so multi-currency drops in later. `[default — overridable]`
- **Time zones:** multi-timezone from day one. All timestamps stored in UTC. Each site stores its IANA timezone. "Weekly" buckets are aligned to **site-local weeks** (a Monday in Boston ≠ a Monday in LA).

---

## 5. Core Concepts & Data Model

All entities carry `org_id`, `created_at`, `updated_at` unless noted.

### 5.1 Entities

**Organization** — tenant root.
`id, name, default_timezone, currency (='USD'), created_at`

**OrgSettings** — one row per org; holds every tunable default surfaced on the Admin settings page (§7.5 / §8.6). Resolved **live** at compute/render time (see §5.2), so changing a default updates everything that inherits it without re-editing each trial.
`id, org_id (1:1),`
`  util_threshold_green_max (numeric, default 70), util_threshold_amber_max (numeric, default 95),`
`  dur_screening_hours (default 5), dur_randomization_hours (default 4), dur_follow_up_hours (default 2), dur_other_hours (default 3),`
`  default_site_hours_per_day (default 10),`
`  default_attrition_curve_id (→ AttritionCurve, default = Standard preset),`
`  default_grid_weeks_visible (default 12), default_horizon_months (default 18)`

**User**
`id, org_id, email (unique per org), password_hash, name, role (enum: org_admin|ops_lead|site_manager|viewer), active (bool)`

**UserSiteAssignment** — many-to-many for site-scoped roles.
`id, user_id, site_id`

**Site**
`id, org_id, name, address, timezone (IANA), operating_weekdays (set, e.g. {Mon..Fri}), hours_per_day (numeric, default 10), rooms (int), active (bool)`

**Trial**
`id, org_id, name, sponsor, protocol_ref, status (enum: draft|planned|active|archived), fpfv (date), lpfv (date), lplv (date), is_multi_arm (bool), enrollment_target (int, trial-level randomization goal), screening_target (int, trial-level screening goal), attrition_curve_id, pending_amendment (bool, default false)`
- `status` lifecycle: **draft** (being set up) → **planned** (fully configured, expected to start in the future, not yet running) → **active** (running now) → **archived** (retired). `planned` and `active` are both forecast-ready and require identical completeness (see §7.1); the distinction exists purely so reporting can separate committed (active) volume from pipeline (planned) volume — see the forecast scope, §6.9.
- `fpfv` = First Patient First Visit (enrollment window start)
- `lpfv` = Last Patient First Visit (enrollment window close — bounds where projections may be non-zero)
- `lplv` = Last Patient Last Visit (trial end — natural forecast horizon for this trial)

**Arm** — single-arm trials get one auto-created "Default Arm" so the UI never forces arm-thinking unless `is_multi_arm`.
`id, trial_id, name`

**Visit** — one SoA row, per arm.
`id, arm_id, name, visit_type (enum: screening|randomization|follow_up|other), target_day_offset (int, days from randomization; negative for screening), window_days (int, ± days), duration_hours_override (numeric, nullable — null inherits the org type default), price (numeric, nullable until pricing step), cost (numeric, nullable — structure only in v1; see §10.1), sort_order (int)`
- The SoA review table *displays* the resolved duration (e.g. a follow-up shows 2h from the org default) but only persists a value here when the user explicitly overrides it. Left null, it tracks the org default live.

**AttritionCurve** — assigned per trial; presets seeded per org.
`id, org_id (nullable for global seeds), name (e.g. Low|Standard|High|custom), total_dropout_pct (numeric), shape (enum/params: backloaded), is_preset (bool)`
- Presets `[default — overridable]`: Low ≈ 10%, Standard ≈ 20%, High ≈ 35% total dropout, concentrated in the back half of the visit sequence. Default assignment = Standard.

**SiteTrial** — assignment of a trial to a site.
`id, site_id, trial_id, per_site_enrollment_target (int, randomization goal), per_site_screening_target (int, screening goal), active (bool)`

**SiteTrialVisitOverride** — site-specific visit duration override (set under trial setup).
`id, site_trial_id, visit_id, duration_hours_override (numeric)`

**EnrollmentWeek** — the projection + actual record. One row per (site, trial, arm, week). Backs the projection-entry grid directly.
`id, site_id, trial_id, arm_id, week_start (date, site-local Monday), proj_screened (int), proj_randomized (int), actual_screened (int, nullable), actual_randomized (int, nullable)`
- Non-zero projections only permitted for `week_start` within `[fpfv, lpfv]`.

**EnrollmentWeekHistory** — audit trail (projections only, per requirement).
`id, enrollment_week_id, field, old_value, new_value, changed_by, changed_at`

**ForecastCache** `[optional, performance]` — memoized engine output per (site, week); recomputed on relevant data change. Engine remains source of truth.

### 5.2 Duration resolution order
For any visit, effective duration = first non-null match of:
1. `SiteTrialVisitOverride.duration_hours_override` (site-specific)
2. `Visit.duration_hours_override` (per-visit explicit override)
3. `OrgSettings` type default for the visit's type (`dur_screening_hours` etc.) — resolved **live**

**Retroactivity of defaults.** All `OrgSettings` values are resolved live, not snapshotted at creation. Changing a type-default duration or an attrition default re-flows immediately to every trial/visit that inherits it (i.e. has no explicit override); display defaults (utilization thresholds, grid window) re-render immediately. Explicit overrides set at the trial/site/visit level are always preserved. This is the whole point of the Admin settings page: refine the model as you learn, and the forecasts update.

### 5.3 Effective enrollment per week (actuals override)
For a given (site, trial, arm, week):
- If `week_start < current_week` **and** actuals entered → use `actual_screened` / `actual_randomized`.
- Else → use `proj_screened` / `proj_randomized`.

---

## 6. Forecast Engine

The engine is the heart of the product. This section is normative; implement it in `/engine` as pure Python with the golden-master test suite as the gate (see §8, Phase 1).

### 6.1 Core idea
Every randomized patient is a deterministic visit-generator. The forecast is the sum of all those generators, modulated by survival and smeared by visit windows.

### 6.2 The five confirmed modeling decisions (load-bearing)
1. **Screening volume is driven directly by the `screened` projection**, not by back-dating randomized patients to a screening visit. Screen-fail attrition lives entirely in the screened-vs-randomized gap and is **not** modeled separately.
2. **Survival/attrition applies only to randomized patients' downstream visits** (randomization, follow-up, other). Never to screening.
3. **Visit-window distribution is triangular**, weighted toward the target day (not uniform across the window).
4. **The forecast range is driven by visit-window timing only**, not by enrollment-projection confidence.
5. **In v1, actuals correct cohort sizes only.** We do not track individual patient visit completion; actually-randomized cohorts are projected forward through the SoA like any other cohort.

### 6.3 Two drivers
- `screened(w)` → **screening-type** visits. `screened(w)` represents patients *entering* screening (their first screening visit) in week `w`. All screened patients are assumed to attend **every** screening visit in the protocol. The first screening visit is anchored to week `w`; subsequent screening visits are placed at their day-offset **relative to the first screening visit** (e.g., a first screening visit at day −28 and a second at day −14 places the second two weeks after the first). **No drop-off is modeled between screening visits** — net screen failure is captured entirely in the screened-vs-randomized gap and realized at the randomization step. Each screening visit therefore carries the full `screened(w)` count and consumes its full duration, so screening capacity load = `screened(w)` × number of screening visits across the relevant weeks. This intentionally errs slightly conservative on screening load (the safe direction for a don't-oversell tool).
- `randomized(w)` → **randomization + follow_up + other** visits, fanning forward from the randomization week through the SoA.

### 6.4 Pseudocode

```python
def compute_forecast(commitments, today, horizon_end):
    # daily_visits[site_id][day][visit_id] -> expected count
    daily = nested_defaultdict(float)

    for c in commitments:                  # c = (site, trial, arm, soa, enrollment_weeks)
        survival = c.attrition_curve.survival_by_visit(c.soa)   # 1.0 at randomization; decays back-loaded
        for w in c.enrollment_weeks:        # each enrollment week with projection/actual
            screened   = effective_screened(c, w)     # actual if past+entered else projected
            randomized = effective_randomized(c, w)

            for v in c.soa.visits:
                if v.visit_type == SCREENING:
                    base   = screened
                    surv   = 1.0
                    anchor = week_start_day(w) + relative_screening_offset(v)
                else:
                    base   = randomized
                    surv   = survival[v.id]
                    anchor = randomization_day(w) + v.target_day_offset

                smear_into(daily[c.site_id], v, base * surv, anchor, v.window_days)

    return aggregate(daily, today, horizon_end)


def smear_into(site_daily, visit, count, anchor_day, window_days):
    # triangular weights over [anchor - window, anchor + window], peak at anchor, normalized to sum 1
    weights = triangular_weights(anchor_day, window_days)
    for day, wt in weights.items():
        site_daily[day][visit.id] += count * wt


def aggregate(daily, today, horizon_end):
    out = {}
    for site_id, days in daily.items():
        for week_start in weeks_between(today_window_start, horizon_end):   # site-local weeks
            visits_by_type = sum_visit_counts_in_week(days, week_start)      # grouped by visit_type
            demand_hours   = sum(count * effective_duration(visit)          # §5.2
                                 for visit, count in visits_in_week(days, week_start))
            capacity_hours = site.rooms * operating_days_in_week(site, week_start) * site.hours_per_day
            utilization    = demand_hours / capacity_hours if capacity_hours else None
            revenue        = sum(count * visit.price for visit, count in visits_in_week(...) if visit.price)
            week_range     = window_spread_bounds(days, week_start)          # earliest/latest placement
            out[(site_id, week_start)] = ForecastCell(
                visits_by_type, demand_hours, capacity_hours, utilization, revenue, week_range)
    return out
```

### 6.5 Outputs
Per (site, week): visit counts by type and by trial; demand hours; capacity hours; utilization %; revenue; and a low/high range from window smearing. Roll-ups: arm → trial → site → network.

### 6.6 Capacity is room-hours
Because durations are type-driven, capacity is **not** a flat visit count. `capacity_hours = rooms × operating_days_in_week × hours_per_day`. Utilization = demand_hours ÷ capacity_hours. Visit counts remain available (tooltips, visit-type view) but the capacity comparison is always in hours.

### 6.7 Golden-master tests (required)
Hand-computed fixtures with known inputs → known outputs covering: single-cohort fan; multi-cohort stacking; survival decay; triangular window smearing across a week boundary; screened-vs-randomized split; hours/capacity; revenue; range bounds; actuals override for past weeks. The engine must reproduce these exactly. This suite is Phase 1's gate.

### 6.8 Enrollment & velocity metrics
A sibling `metrics` module in the engine package computes operational metrics from the same inputs (`EnrollmentWeek` data + targets + FPFV/LPFV). Pure functions, unit-tested alongside the forecast. Computed per trial, per site, and aggregate, over a selectable window (using actuals where available, projections otherwise):

- **Screen Fail Rate (SFR)** = (screened − randomized) ÷ screened.
- **Screen rate** = screened ÷ active sites ÷ weeks.
- **Enrollment rate** = randomized ÷ active sites ÷ weeks.
- **Pace vs plan** = cumulative actual randomized to date ÷ cumulative projected randomized to date (>100% = ahead of own plan, <100% = behind). Uses the site's own projection curve as the expected pace rather than assuming linear.
- **Enrollment health (projected vs goal)** = total expected randomized by LPFV ÷ randomization goal; the parallel screened-vs-screening-goal figure is computed the same way. Same basis as the projection variance, surfaced as a health indicator.
- **Week-over-week** = current vs previous week counts (screens, randomizations, visits, revenue).

**Limitation to honor:** true cycle-time "speed" (e.g., screen-to-randomization interval) requires patient-level timing, which v1 does not track (aggregate actuals only). It is deferred alongside individual visit-level actuals (§10.1). The velocity metrics above are all computable from aggregate weekly data.

### 6.9 Forecast scope (trial status)
The engine itself is status-agnostic — it forecasts whatever cohorts it is handed. **Selection by trial status happens in the application layer, never in `/engine`** (golden rule #2). The forecast/metrics surfaces accept a **scope** selecting which trials contribute:

- **Active** *(default)* — only `active` trials. Preserves the original "forecast committed work" behavior; this is what every view shows unless the operator chooses otherwise.
- **Planned** — only `planned` trials. The future pipeline in isolation.
- **Combined** — `active` + `planned` together, for the total expected picture.

`draft` and `archived` trials are never forecast under any scope. Because a `planned` trial carries a future FPFV and future-dated enrollment weeks, it naturally contributes ~zero demand in the near term and ramps when it starts — so Combined is a true superset of Active, not a double-count. Scope applies uniformly to the network forecast, per-site forecast, capacity/utilization metrics, and exports, so a report can always state which scope it reflects.

---

## 7. Workflows

### 7.1 Trial setup wizard
Guided wizard, **basics required up front**, then resumable in any order via "Save & exit." Steps:
1. **Basics** (required): name, sponsor, FPFV, LPFV, LPLV, single/multi-arm.
2. **Schedule of activities:** upload protocol PDF → background AI parse → **editable review table** (visit name, type, target day, window, duration). AI flags low-confidence rows (esp. visit type) with a visual marker; confident rows left clean. User confirms. Multi-arm trials show an arm selector with one SoA per arm. Manual entry is the fallback path.
3. **Sites & targets:** assign sites; set per-site enrollment target; optional site-specific duration overrides.
4. **Visit pricing:** assign a USD price to each confirmed visit (uniform across sites).
5. **Attrition:** assign a curve (default Standard).
6. **Activate / mark planned:** a fully set-up trial flips Draft → **Active** (running now) or Draft → **Planned** (configured but starting in the future). Both transitions require identical completeness (SoA with a randomization visit, ≥1 assigned site, attrition curve assigned; pricing **not** required). A Planned trial flips to Active when it actually starts. See §6.9 for how the two statuses are reported separately.

Rules: **a trial must be fully set up (Active or Planned) before any projection can be entered against it** — Planned trials carry their (future-dated) enrollment projections just like Active ones, which is what makes the pipeline forecastable. Org Admin and Ops Lead can create/configure trials; Site Manager and Viewer cannot. A trial is "volume-ready" once SoA + sites + attrition exist, and "revenue-ready" once prices are entered.

### 7.2 Site setup
Attributes per §5.1 Site. Operating days are **specific weekdays**. Active/inactive flag (disable without delete). Site-specific visit durations are configured under trial setup (site-specific config), not here.

### 7.3 Projection & actuals entry — the adoption-critical surface
Spreadsheet-style grid for one (site, trial, arm), weeks as rows, columns grouped **Projected** (screened, randomized) and **Actual** (screened, randomized). `[default — overridable: weeks as rows vs. columns]`

- **Past weeks:** projection cells locked (preserve historical projection for variance); actual cells active.
- **Current week:** both editable; row visually highlighted.
- **Future weeks:** projection cells active; actual cells greyed.
- A horizontal divider separates the actuals period from the projection period.
- **Validation:** warn-and-allow when site projections don't sum to the trial targets. Show the variance against **both** goals — randomized vs randomization target and screened vs screening target (e.g., "Randomized 87 / goal 100 · 13 under; Screened 140 / goal 150 · 10 under") — everywhere projections appear; never block the save.
- **Audit trail:** every projection edit recorded (who/when/old→new), surfaced via "View change history."
- **Keyboard navigation is a first-class acceptance criterion**, not a nice-to-have: Tab/Shift-Tab across, Enter to drop a row, arrow keys in all four directions, and clipboard paste to fill a block from Excel. Disabled cells are skipped during keyboard movement.

Built on TanStack Table (headless) — these spreadsheet behaviors are implemented by us and get a dedicated smoke test.

### 7.4 Export
PDF snapshot of the current view (grid or chart) + CSV of underlying numbers. Available from the network grid and per-site views.

### 7.5 Admin settings (Org Admin only)
A dedicated settings area, role-gated to Org Admin, where every tunable default in the system can be changed after the fact. Backed by `OrgSettings` (§5.1); all values resolve live (§5.2), so edits take effect on the next forecast render. Sections:

- **Forecasting defaults:** visit-type durations (screening / randomization / follow-up / other hours); manage attrition curve presets (name, total dropout %, shape) and set the default curve assigned to new trials.
- **Display defaults:** utilization color thresholds (green max %, amber max %); default grid weeks visible; default forecast horizon (months).
- **Org defaults:** default site hours/day; organization timezone; currency (USD-locked in v1, field present for future multi-currency).
- **User management** lives in this area too (create/deactivate users, assign roles and site scopes) — already an Org Admin capability per §3.

Editing a default that has live inheritors (e.g. changing follow-up duration from 2h to 3h) should show a brief confirmation noting it will re-flow to all trials/visits without an explicit override; explicit overrides are never touched.

---

## 8. Product Surface (Views)

### 8.1 Network grid — anchor view
- Rows = sites; columns = weeks (~12 visible `[default]`, scrollable to horizon).
- Cells shaded by utilization: green < 70%, amber 70–95%, red > 95% `[default — overridable thresholds]`. Over-100% is the critical state and must read loudly.
- KPI strip: active sites, forecast revenue (visible window), avg utilization, **sites at risk** (danger-colored headline).
- Cells show utilization %; raw visits/capacity on hover.
- Past weeks (actuals) / current / future (projections) labeled above the grid.
- Click a row/cell → per-site chart.

### 8.2 Per-site chart — diagnostic drill-down
- Breadcrumb back to network; Export button.
- KPI strip: current utilization, active trials, **projected overage** (first future week demand exceeds capacity; "—" if none), forecast revenue.
- Stacked area chart, y-axis = **room-hours/week**, flat capacity line, dashed "now" marker.
- **Toggle: Stack by Trial / Visit type.** Trial view = one band per trial. Visit-type view = screening/randomization/follow-up/other. Both sum to the same weekly totals.
- Each trial gets a persistent color reused across all views. Legend above the chart; interactive (click to isolate) in production.

### 8.3 Trial detail — deepest drill-down (read-only)
Network → site → trial. Shows a single trial's SoA, assigned attrition curve, projections vs. actuals, and its forecast contribution at that site. Composes already-specified components.

### 8.4 Enrollment metrics view
Study-level and site-level tables surfacing the §6.8 metrics: screened, randomized, SFR, screen rate, enrollment rate, pace vs plan, and enrollment health against both the randomization and screening goals — plus a week-over-week comparison. Selectable window. Key metrics (pace, health, SFR) also appear as a compact panel on the per-site chart and trial detail views. This is the "are we enrolling fast enough?" companion to the "do we have capacity?" forecast.

### 8.5 Calendar view (per site)
A month-calendar heatmap for a site: each day colored by that day's utilization (same green/amber/red scale as the network grid), driven by the engine's daily output (§6.4). Lets a site manager see *which days* of a month are heavy, not just which weeks. Month navigation; click a day to see its visit breakdown.

### 8.6 Admin settings page (Org Admin only)
The UI for §7.5. Grouped sections (Forecasting defaults, Display defaults, Org defaults, User management) with pre-styled form inputs and inline save. Role-gated; hidden from non-admins. Every value shows its current setting and resets cleanly to the seeded default.

### 8.7 Deferred interactions (NOT in v1)
Filtering/segmentation; time-travel comparison ("grid as of last month"); decision/annotation log; proactive alerts; capacity what-if. Captured here so they are not lost; revisit in v1.5.

---

## 9. Implementation Plan

### 9.1 Process requirements (apply to every phase)
- **Phased build with hard gates.** A phase does not start until the prior gate passes.
- **Each gate = automated smoke test (script exercising the critical path) + manual smoke checklist.** No building on unverified foundations.
- **`/docs/phase.md`** — living tracker: per-phase status (done / in-progress / blocked), gate results, dates. Updated continuously.
- **`/docs/architecture.md`** — living Mermaid dependency diagram of modules/services and their connections, updated **every phase**, so nothing ends up orphaned or isolated.

### 9.2 Phases

**Phase 0 — Foundations.** Monorepo scaffold, Docker Compose, Postgres, FastAPI skeleton, React skeleton, CI. Auth (email/password, Argon2, cookie sessions). Org & User models, RBAC, multi-tenancy (`org_id` + RLS).
*Gate:* create an org, log in, role-scoped access enforced; RLS verified to block cross-org reads.

**Phase 1 — Forecast engine (standalone, highest-risk-first).** Implement §6 in `/engine` with the full golden-master suite, including the §6.8 enrollment/velocity `metrics` module. No UI, no DB.
*Gate:* engine reproduces all golden-master fixtures exactly (cohort fan, stacking, survival, triangular smearing, screened/randomized split, hours/capacity, revenue, range, actuals override) and the metrics functions (SFR, screen/enrollment rate, pace vs plan, enrollment health, week-over-week) match hand-computed fixtures.

**Phase 2 — Core data model & CRUD.** Sites, Trials (with both randomization and screening goals), Arms, Visits/SoA (manual entry, including the structure-only `cost` field), AttritionCurves, SiteTrial (per-site randomization + screening targets), pricing, overrides, and `OrgSettings` (seeded with the default values from §5.1). Duration/attrition/threshold resolution reads live from `OrgSettings` (§5.2). Migrations + API.
*Gate:* set up a site and a full trial end-to-end via API; validations (FPFV/LPFV bounds, draft→active completeness) enforced; data persists; changing an `OrgSettings` value re-flows to inheriting entities.

**Phase 3 — Projections & actuals.** EnrollmentWeek model + audit history; the TanStack spreadsheet grid with keyboard nav + paste; warn-and-allow variance.
*Gate:* enter projections and actuals; keyboard nav + paste work; past projections locked; audit history records edits; variance computes against target.

**Phase 4 — Forecast wiring & views.** Connect engine to persisted data; network grid + per-site chart (with toggle) + trial detail; the enrollment metrics view (§8.4) and the per-site calendar view (§8.5).
*Gate:* rendered forecasts match engine golden values for a seeded dataset; drill-down network→site→trial works; room-hours capacity comparison correct; metrics tables (SFR, rates, pace, health vs both goals) and the calendar heatmap render from real data.

**Phase 5 — Trial setup wizard + AI SoA parsing.** Wizard flow; Claude API (vision) PDF parse → structured JSON → editable review with flagged uncertain rows; visit-type classification; resumable Draft state.
*Gate:* upload a real protocol PDF, parse, correct flagged rows, complete wizard, activate trial, see it appear in the forecast.

**Phase 6 — Admin settings, exports & commercialization polish.** Admin settings page (§7.5 / §8.6) exposing all `OrgSettings` defaults + user management; PDF + CSV export; new-org onboarding flow; empty/error states; polish to demo bar.
*Gate:* an Org Admin can tune a default (e.g. follow-up duration) and see forecasts re-flow; exports produce correct PDF/CSV; a fresh org can be stood up and demoed end-to-end.

### 9.3 Phase ordering rationale
The engine (Phase 1) is built and proven in isolation immediately after foundations — applying the "don't build on faulty code" principle to the single riskiest, trust-critical component before any UI depends on it.

---

## 10. Out of Scope (v2+) & Open Risks

### 10.1 Deferred to v2+
- **What-if simulation** (the engine is built to accept hypothetical commitments so this is additive, not a refactor).
- **CTMS integration** (any source; each is its own multi-month effort).
- **AI budget parsing** for visit pricing (manual in v1).
- **SSO / SAML** (auth module is SSO-ready).
- **Multi-currency** (money fields carry currency now).
- **Proactive alerts, decision/annotation log, time-travel comparison, filtering, capacity what-if** (see §8.7).
- **Per-visit-completion actuals** (v1 tracks aggregate randomization only).
- **Recruitment / pre-screening funnel** (outreach → contact → prescreen → screening-scheduled → screened → randomized, with Sankey and funnel analytics). Explicitly parked for now — revisit after v1; the `screened` projection is the natural seam where it would connect.
- **Cost & margin analytics** (revenue − cost, profitability, staff-cost-based capacity). The `Visit.cost` field exists as structure in v1, but no cost computation, margin reporting, or staffing model is built.

### 10.2 Open risks
- **AI SoA parsing fidelity.** Real protocol SoAs have multi-page tables, merged cells, footnotes modifying timing, and arm/cohort variations. Mitigation: mandatory human review step with low-confidence flagging; manual entry fallback; never let parser output flow into forecast math unconfirmed.
- **TanStack spreadsheet behaviors.** Keyboard nav + paste are custom on headless TanStack Table. Mitigation: dedicated component + smoke test in Phase 3.
- **Forecast trust calibration.** Hitting ~10–15% accuracy depends on projection quality and consistent actuals entry. Mitigation: variance reporting to make accuracy visible and improvable over time.

### 10.3 Open items to confirm at review
All three are now **tunable post-launch via the Admin settings page (§7.5 / §8.6)**, so picking a starting value is low-stakes — they no longer block the build. Confirm the seeds when convenient:
- Network grid utilization thresholds (70/95).
- Projection grid orientation (weeks as rows vs. columns) — note: this is the one item *not* in Admin settings; it's a layout decision, so flag it if you want it flipped.
- Type-default durations (5/4/2/3 hrs) and attrition presets (10/20/35%).
