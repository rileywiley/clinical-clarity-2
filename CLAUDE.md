# CLAUDE.md — Volume Forecasting Platform

Operating contract for Claude Code on this project. Read every session. Keep it short.
**`docs/prd.md` is the source of truth for *what* to build.** This file is *how* we work.
If the two ever conflict, stop and ask the human.

---

## Golden rules — never violate

1. **Gate before you proceed.** Never start a phase until the prior phase's gate passes — both the automated smoke test *and* the manual smoke checklist. Do not build on a failing or skipped gate. Phases and gates are defined in PRD §9.
2. **The engine stays pure.** `/engine` is pure Python. No web, DB, HTTP, ORM, or framework imports — ever. It takes data in and returns results. This is what makes the math testable and reusable for v2 simulation.
3. **Golden masters stay green.** The engine's golden-master and metrics test suites must pass before any work proceeds on top of the engine. A red suite blocks everything downstream.
4. **Keep the maps current.** At the end of every phase (and whenever structure changes), update `docs/phase.md` (status + gate results) and `docs/architecture.md` (Mermaid dependency diagram). The diagram exists so nothing ends up orphaned or isolated — if a module isn't on it, it's not done.
5. **Don't drift the model.** The five forecast modeling decisions in PRD §6.2 are load-bearing. Do not silently change them (summary below).
6. **Tenant isolation is absolute.** Every table carries `org_id`; every query is org-scoped; Postgres RLS is enforced. Never write a query or endpoint that can read across orgs.

---

## The five load-bearing modeling decisions (PRD §6.2)

1. Screening volume is driven by the `screened` projection directly — not back-dated from randomized patients. Screen-fail attrition lives in the screened-vs-randomized gap; it is not modeled separately.
2. Survival/attrition applies only to randomized patients' downstream visits, never to screening.
3. Visit-window distribution is triangular, weighted toward the target day.
4. The forecast range comes from visit-window timing only, not enrollment-projection confidence.
5. v1 actuals correct cohort sizes only — no individual visit-completion tracking.

---

## Project layout

```
/engine     pure forecast + metrics (numpy/pandas), golden-master tests. NO web/db deps.
/backend    FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic migrations, API, auth
/frontend   React + TypeScript + Vite + Tailwind
/docs       prd.md (spec), phase.md (progress), architecture.md (dependency diagram)
docker-compose.yml
```

---

## Stack & conventions

- **Backend:** FastAPI · SQLAlchemy 2.0 · Pydantic v2 · Alembic. Full type hints. Format/lint before commit.
- **Frontend:** React + TS + Vite + Tailwind + TanStack Query + TanStack Table + Recharts.
  TanStack Table is headless — the spreadsheet behaviors (keyboard nav: Tab/Shift-Tab/Enter/arrows, plus clipboard paste) are hand-built and are a **first-class acceptance criterion** with their own tests, not a nice-to-have (PRD §7.3).
- **DB:** PostgreSQL. Money fields carry an explicit currency (USD in v1). Timestamps stored UTC; weekly buckets are **site-local** weeks.
- **Auth:** cookie sessions + Argon2. Built to accept SSO later — don't bake in assumptions that block it.
- **Defaults:** all tunable defaults (durations, utilization thresholds, attrition presets, etc.) live in `OrgSettings` and resolve **live** (PRD §5.2). Never hardcode these in code — read them from settings.
- **AI SoA parsing:** Claude API (vision) → structured JSON → human review. Parser output never flows into forecast math unconfirmed.

---

## Commands

> Confirm/adjust these during the Phase 0 scaffold, then keep this section accurate.

- Engine tests: `pytest engine/`
- Backend tests: `pytest backend/`
- Frontend tests: `npm --prefix frontend test`
- Lint/format: `ruff check . && ruff format .` (backend/engine); `npm --prefix frontend run lint`
- Migrations: `alembic -c backend/alembic.ini revision --autogenerate -m "..."` then `alembic ... upgrade head`
- Dev (all services): `docker compose up`
- Frontend dev server: `npm --prefix frontend run dev`

---

## Working agreements

- **New behavior gets a test.** Engine and metrics changes get golden-master fixtures with hand-computed expected values.
- **Stay in scope.** Do not build deferred items (PRD §10.1) without explicit human sign-off: what-if simulation, CTMS integration, AI budget parsing, SSO, multi-currency, cost/margin analytics, the recruitment funnel, and per-visit-completion actuals. The `Visit.cost` field is structure-only — do not build cost/margin logic on it yet.
- **Read before writing.** When touching a domain, read the relevant PRD section first; cite the section in your plan.
- **One open layout question remains:** projection grid orientation (weeks as rows vs. columns) — rows unless the human says otherwise (PRD §7.3 / §10.3).
- **Keep this file lean** (~150 lines max). Long or path-specific rules go in `.claude/rules/`.
