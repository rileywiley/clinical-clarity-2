# Architecture — dependency diagram

Per CLAUDE.md golden rule #4, this diagram is **updated every phase**. If a module isn't on the diagram, it isn't done. The goal is to make orphaned or isolated modules obvious at a glance.

**Last refreshed:** 2026-06-24 (Phase 0 ✅ · Phase 1 ✅ · Phase 2 ✅ · Phase 3 ✅ · Phase 4 ✅ · Phase 5 🟡 — first LLM call ships, arq worker live, MinIO/S3 wired)

## Top-level system

```mermaid
flowchart LR
  subgraph Client["frontend (React+TS+Vite+Tailwind)"]
    APP[App.tsx]
    PAGES["pages: Login, NetworkGrid, ProjectionGrid,<br/>SiteChart, SiteCalendar, TrialDetail, Metrics,<br/>TrialWizard (Phase 5)"]
    SOA["components/SoaReviewTable (Phase 5)<br/>confidence bands + blocking"]
    SHELL["components/AppShell<br/>(top bar w/ user + sign out)"]
    API_CLIENT[api.ts]
    SHEET["components/SpreadsheetGrid<br/>(headless: useKeyboardNav,<br/>useClipboardPaste)"]
    VAR["components/VarianceHint<br/>HistoryDrawer"]
    KPI["components/KpiStrip<br/>TrialColorBadge"]
    GUARD["hooks/useUnsavedChangesGuard<br/>(useBlocker + beforeunload)"]
    LIB["lib/trialColors (djb2 hash → palette)<br/>lib/utilization (band classifier)<br/>lib/formatters"]
    APP --> SHELL
    SHELL --> PAGES
    APP --> API_CLIENT
    PAGES --> SHEET
    PAGES --> VAR
    PAGES --> KPI
    PAGES --> GUARD
    PAGES --> LIB
    PAGES --> SOA
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
      R_EW["routers.enrollment_weeks<br/>(bulk PUT, history, variance)"]
      R_FC["routers.forecast<br/>(network, site, trial, calendar, metrics,<br/>active-trials)"]
      R_DOC["routers.documents (Phase 5)<br/>(upload, parse-job apply/discard)"]
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
      M_EW[EnrollmentWeek]
      M_EWH[EnrollmentWeekHistory]
      M_DOC["Document (Phase 5)"]
      M_SPJ["SoaParseJob (Phase 5)<br/>parsed_visits JSONB"]
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
      M_EW --> M_BASE
      M_EWH --> M_BASE
    end

    subgraph Services
      SVC_RES["resolution<br/>(live-read OrgSettings → effective duration)"]
      SVC_ACT["trial_activation<br/>(draft→active validator)"]
      SVC_AUDIT["enrollment_audit<br/>(diff projection fields, write history rows)"]
      SVC_VAR["enrollment_variance<br/>(sum sites vs trial targets, warn-and-allow)"]
      SVC_FA["forecast_adapter<br/>(DB → Commitment → engine)"]
      SVC_MA["metrics_adapter<br/>(DB → engine.compute_metrics)"]
      SVC_CLAUDE["claude_soa (Phase 5)<br/>system prompt + caching<br/>+ messages.parse"]
      SVC_STORAGE["storage<br/>(S3/MinIO via aiobotocore)"]
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
    R_EW --> SVC_AUDIT
    R_EW --> SVC_VAR
    SVC_AUDIT --> M_EW
    SVC_AUDIT --> M_EWH
    SVC_VAR --> M_EW
    SVC_VAR --> M_TRIAL
    R_EW --> M_EW
    R_EW --> M_EWH
    R_FC --> SVC_FA
    R_FC --> SVC_MA
    SVC_FA --> M_SITE
    SVC_FA --> M_TRIAL
    SVC_FA --> M_ARM
    SVC_FA --> M_VISIT
    SVC_FA --> M_CURVE
    SVC_FA --> M_EW
    SVC_FA --> M_ORGSET
    SVC_FA --> M_STRIAL
    SVC_FA --> M_STVO
    SVC_MA --> M_EW
    SVC_MA --> M_TRIAL
    SVC_MA --> M_STRIAL
    R_DOC --> SVC_STORAGE
    R_DOC --> M_DOC
    R_DOC --> M_SPJ
    R_DOC --> M_VISIT
  end

  subgraph Data
    PG[("PostgreSQL 16<br/>RLS on users, organizations<br/>app_owner BYPASSRLS · app_user RLS-enforced")]
    RD[("Redis 7 — idle")]
  end

  WORKER["arq worker (live, Phase 5)<br/>parse_soa job"]
  MINIO[("MinIO / S3<br/>document storage")]
  CLAUDE_API[("Anthropic API<br/>claude-opus-4-7")]
  ALEMBIC["alembic migrations<br/>(runs as app_owner)"]

  subgraph ENG["engine (pure Python — zero web/DB imports)"]
    direction TB
    ENG_TYPES["types: Site, Trial, Arm, Visit,<br/>AttritionCurve, EnrollmentWeek,<br/>Commitment, ForecastCell, MetricsRow"]
    ENG_WINDOWS["windows: triangular_weights"]
    ENG_ATTRITION["attrition: linear back-loaded survival"]
    ENG_DURATION["duration: PRD §5.2 resolution order"]
    ENG_FORECAST["forecast: compute_forecast + compute_daily_forecast"]
    ENG_METRICS["metrics: SFR, rates, pace, health, WoW"]
    ENG_FORECAST --> ENG_WINDOWS
    ENG_FORECAST --> ENG_ATTRITION
    ENG_FORECAST --> ENG_DURATION
    ENG_FORECAST --> ENG_TYPES
    ENG_METRICS --> ENG_TYPES
  end

  SVC_FA -- "feeds Commitment dataclasses" --> ENG_FORECAST
  SVC_MA -- "feeds EnrollmentWeek dataclasses" --> ENG_METRICS

  Client -- "cookie auth via /api proxy" --> MAIN
  Backend -- "asyncpg as app_user" --> PG
  ALEMBIC --> PG
  WORKER --> RD
  WORKER --> PG
  WORKER --> MINIO
  WORKER --> CLAUDE_API
  Backend --> MINIO
```

## Notes

- **`engine`** is now wired (Phase 4) via `forecast_adapter` and `metrics_adapter`. The engine still has **no outgoing edges** outside the package — that's enforced by `tests/test_engine_purity.py`, which still passes after wiring. CLAUDE.md golden rule #2 holds. The adapters are the *only* modules that touch both worlds: they read SQLAlchemy ORM objects from Postgres, convert them to the engine's plain frozen dataclasses (`Commitment`, `EnrollmentWeek`, etc.), and hand them to the engine.
- **`OrgSettings`** is now wired (Phase 2). The resolution service reads it live on every call — a PATCH to its duration fields immediately re-flows to every inheriting trial/visit. Explicit overrides at the visit or site-trial level are preserved.
- **`AttritionCurve`** is the only org-scoped table whose RLS policy admits NULL `org_id` rows (for future global seeds). No global seeds ship in v1; the column shape is in place.
- **Service layer** (`app/services/`) is new in Phase 2. `resolution.py` is intentionally the same shape as `engine/duration.py` — Phase 4 will use it to build the `OrgDurationDefaults` dataclass that gets handed into the engine. `trial_activation.py` returns a structured failure list rather than fail-fast, so the wizard UI in Phase 5 can surface every blocker together. Phase 3 added `enrollment_audit.py` (one history row per *changed* projection field; actuals are never audited) and `enrollment_variance.py` (PRD §7.3 warn-and-allow, never blocks).
- **SpreadsheetGrid** (frontend, Phase 3) is built generic over a row shape. Phase 4's NetworkGrid uses a purpose-built `<table>` instead — sites-as-rows × weeks-as-columns with hover tooltips and click-to-drill was different enough that a dedicated component was clearer than over-loading the spreadsheet primitive. Both serve different needs; both are well-tested.
- **Trial colors are deterministic** (`lib/trialColors.ts`, djb2 hash of `trial_id` → fixed 12-color palette). Same color everywhere — network legend, per-site chart series, trial-detail header, metrics-page badges. No DB column needed.
- **`/active-trials`** lives at the top level, **not** at `/trials/active`. FastAPI matches `/trials/{trial_id}` first and would try to parse "active" as a UUID. Caught during Phase 4 smoke; named to be self-documenting.
- **`useUnsavedChangesGuard`** is the project-wide form-exit guard (per saved feedback memory: every Save-button form must use it). Hooks into React Router 6's `useBlocker` for in-app navigation and `beforeunload` for tab close. Phase 5's trial setup wizard and Phase 6's admin settings page will both reuse it.
- **`arq worker`** is now live (Phase 5). One job: `parse_soa(document_id, org_id, parse_job_id)` pulls the PDF from S3/MinIO, calls Claude with the cached system prompt, persists `parsed_visits` + `raw_output` to the `SoaParseJob` row. Failures get a `failed` status with the error message so the user can retry.
- **`Document` / `SoaParseJob`** (Phase 5) keep AI output **out** of the engine until the user confirms. The engine reads `Visit` rows; `parsed_visits` stays in JSONB until the apply endpoint creates real Visit rows from the user's *edited* payload. This is the PRD §10.2 mitigation made structural.
- **`claude_soa`** is the only module that holds the SoA system prompt. Versioned via `PROMPT_VERSION`. The Anthropic client is dependency-injected so tests pass a mock; the real API is only called from the worker (and the manual smoke).
- **`storage`** wraps `aiobotocore`. Same code path serves AWS S3 (prod) and MinIO (dev) — only the endpoint URL differs. Bucket is created idempotently by the `minio-init` one-shot in docker-compose.
- **Two-role DB split** (`app_owner` BYPASSRLS for Alembic, `app_user` RLS-enforced at runtime) is what makes tenant isolation auditable, not just intended.
- Every domain model inherits `OrgScopedMixin` (carries `org_id`) except `Organization` itself.
- Every request runs inside a transaction with `SET LOCAL app.current_org_id = '<uuid>'`; RLS policies on each org-scoped table read that via `current_setting('app.current_org_id')`.
- The `/auth/login` route binds the requested `org_id` as the tenant *before* the user lookup so RLS doesn't hide the row being authenticated against — UUIDs aren't enumerable, so this doesn't leak.
- Frontend dev hits the backend via Vite's `/api` proxy, keeping both on the same origin in dev so the session cookie round-trips without CORS gymnastics.
