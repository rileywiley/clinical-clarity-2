# Volume Forecasting Platform

Multi-tenant SaaS that forecasts weekly clinical-trial visit volume per site vs. site capacity (room-hours), so a trial-network executive can decide where there's room to sell and where capacity is at risk.

- **What we're building:** see [`docs/prd.md`](docs/prd.md) — the source of truth.
- **How we're building it:** see [`CLAUDE.md`](CLAUDE.md) — the operating contract (gates, golden rules, conventions).
- **Where we are right now:** see [`docs/phase.md`](docs/phase.md) — phase tracker with gate results.
- **How the modules fit together:** see [`docs/architecture.md`](docs/architecture.md) — Mermaid dependency diagram.

## Repo layout

```
/engine     pure-Python forecast engine + golden-master tests (no web/db deps)
/backend    FastAPI app, SQLAlchemy models, Alembic migrations, API routes, auth
/frontend   React + TypeScript + Vite + Tailwind
/docs       prd.md (spec), phase.md (progress), architecture.md (diagram)
```

## Local development

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), Python 3.12, Node 20+.

```sh
docker compose up
```

Backend on http://localhost:8000, frontend on http://localhost:5173, Postgres on host port `55432` (container-internal 5432).

For component-level work, see each package's own README (or run `uv run pytest` in `engine/`/`backend/` and `pnpm dev` in `frontend/`).
