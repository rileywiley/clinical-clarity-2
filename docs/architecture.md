# Architecture — dependency diagram

Per CLAUDE.md golden rule #4, this diagram is **updated every phase**. If a module isn't on the diagram, it isn't done. The goal is to make orphaned or isolated modules obvious at a glance.

**Last refreshed:** 2026-05-28 (Phase 0 ✅ · Phase 1 ✅ · Phase 2 🟡 deliverables done, awaiting smoke)

## Top-level system

```mermaid
flowchart LR
  subgraph Client["frontend (React+TS+Vite+Tailwind)"]
    APP[App.tsx]
    PAGES[pages: Login, Home]
    API_CLIENT[api.ts]
    APP --> PAGES
    APP --> API_CLIENT
  end

  subgraph Backend["backend (FastAPI)"]
    MAIN[main.create_app]
    direction TB

    subgraph Routers
      R_HEALTH[routers.health]
      R_AUTH[routers.auth]
      R_ORGS["routers.orgs<br/>(now seeds OrgSettings + 3 presets)"]
      R_ORGSET[routers.org_settings]
      R_SITES[routers.sites]
      R_CURVES[routers.attrition_curves]
      R_TRIALS["routers.trials<br/>(CRUD + activate + arms nested)"]
      R_VISITS[routers.visits]
      R_STRIALS[routers.site_trials]
    end

    subgraph Core
      CFG[config: Settings]
      SEC[security: Argon2 + signed cookies]
      DB[db: engine, sessionmaker, set_tenant]
      DEPS[deps: get_db, get_current_user, require_role]
    end

    subgraph Models
      M_BASE[base: Base, OrgScopedMixin, TimestampMixin]
      M_ORG[Organization]
      M_USER["User + UserRole enum"]
      M_ORGSET[OrgSettings]
      M_CURVE[AttritionCurve]
      M_SITE[Site]
      M_TRIAL["Trial + TrialStatus enum"]
      M_ARM[Arm]
      M_VISIT["Visit + VisitType enum"]
      M_STRIAL[SiteTrial]
      M_STVO[SiteTrialVisitOverride]
      M_ORG --> M_BASE
      M_USER --> M_BASE
      M_ORGSET --> M_BASE
      M_CURVE --> M_BASE
      M_SITE --> M_BASE
      M_TRIAL --> M_BASE
      M_ARM --> M_BASE
      M_VISIT --> M_BASE
      M_STRIAL --> M_BASE
      M_STVO --> M_BASE
    end

    subgraph Services
      SVC_RES["resolution<br/>(live-read OrgSettings → effective duration)"]
      SVC_ACT["trial_activation<br/>(draft→active validator)"]
    end

    MAIN --> Routers
    R_AUTH --> SEC
    R_AUTH --> DB
    R_ORGS --> DB
    R_ORGS --> SEC
    Routers --> DEPS
    DEPS --> SEC
    DEPS --> DB
    DEPS --> M_USER
    DB --> CFG
    R_ORGS --> M_ORG
    R_ORGS --> M_USER
    R_ORGS --> M_ORGSET
    R_ORGS --> M_CURVE
    R_TRIALS --> SVC_ACT
    SVC_ACT --> M_TRIAL
    SVC_ACT --> M_VISIT
    SVC_ACT --> M_STRIAL
    SVC_RES --> M_ORGSET
    SVC_RES --> M_VISIT
    SVC_RES --> M_STVO
  end

  subgraph Data
    PG[("PostgreSQL 16<br/>RLS on users, organizations<br/>app_owner BYPASSRLS · app_user RLS-enforced")]
    RD[("Redis 7 — idle")]
  end

  WORKER["arq worker — idle until Phase 5"]
  ALEMBIC["alembic migrations<br/>(runs as app_owner)"]

  subgraph ENG["engine (pure Python — zero web/DB imports)"]
    direction TB
    ENG_TYPES["types: Site, Trial, Arm, Visit,<br/>AttritionCurve, EnrollmentWeek,<br/>Commitment, ForecastCell, MetricsRow"]
    ENG_WINDOWS["windows: triangular_weights"]
    ENG_ATTRITION["attrition: linear back-loaded survival"]
    ENG_DURATION["duration: PRD §5.2 resolution order"]
    ENG_FORECAST["forecast: compute_forecast"]
    ENG_METRICS["metrics: SFR, rates, pace, health, WoW"]
    ENG_FORECAST --> ENG_WINDOWS
    ENG_FORECAST --> ENG_ATTRITION
    ENG_FORECAST --> ENG_DURATION
    ENG_FORECAST --> ENG_TYPES
    ENG_METRICS --> ENG_TYPES
  end

  Client -- "cookie auth via /api proxy" --> MAIN
  Backend -- "asyncpg as app_user" --> PG
  ALEMBIC --> PG
  WORKER --> RD
  WORKER --> PG
```

## Notes

- **`engine`** has internal structure now (forecast + metrics + helpers + types) but still no *outgoing* edges to anything outside the package — that's enforced by `tests/test_engine_purity.py` (walks every submodule and asserts no forbidden imports leaked into `sys.modules`). It'll get an *incoming* edge from the backend in Phase 4 (forecast wiring). Until then it remains in-tree but deliberately decoupled per CLAUDE.md golden rule #2.
- **`OrgSettings`** is now wired (Phase 2). The resolution service reads it live on every call — a PATCH to its duration fields immediately re-flows to every inheriting trial/visit. Explicit overrides at the visit or site-trial level are preserved.
- **`AttritionCurve`** is the only org-scoped table whose RLS policy admits NULL `org_id` rows (for future global seeds). No global seeds ship in v1; the column shape is in place.
- **Service layer** (`app/services/`) is new in Phase 2. `resolution.py` is intentionally the same shape as `engine/duration.py` — Phase 4 will use it to build the `OrgDurationDefaults` dataclass that gets handed into the engine. `trial_activation.py` returns a structured failure list rather than fail-fast, so the wizard UI in Phase 5 can surface every blocker together.
- **`arq worker`** has no work yet but the container is wired so the Phase 5 hookup (Claude vision SoA parser) is a code change, not infra.
- **Two-role DB split** (`app_owner` BYPASSRLS for Alembic, `app_user` RLS-enforced at runtime) is what makes tenant isolation auditable, not just intended.
- Every domain model inherits `OrgScopedMixin` (carries `org_id`) except `Organization` itself.
- Every request runs inside a transaction with `SET LOCAL app.current_org_id = '<uuid>'`; RLS policies on each org-scoped table read that via `current_setting('app.current_org_id')`.
- The `/auth/login` route binds the requested `org_id` as the tenant *before* the user lookup so RLS doesn't hide the row being authenticated against — UUIDs aren't enumerable, so this doesn't leak.
- Frontend dev hits the backend via Vite's `/api` proxy, keeping both on the same origin in dev so the session cookie round-trips without CORS gymnastics.
