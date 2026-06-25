FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# uv from the official distroless image — no curl/install gymnastics.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

WORKDIR /app

# The backend depends on the local /engine package as an editable path source
# (`engine = { path = "../engine" }`). uv must read engine's metadata while
# resolving backend deps, so the engine source has to exist on disk first.
# Placed at /engine so `../engine` resolves from the backend root at /app — the
# same relative layout as the repo. (Build context is the repo root.)
COPY engine/ /engine/

# Install deps in a separate layer for cache efficiency. Both syncs run from
# /app so the `../engine` path source resolves identically in each.
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --no-install-project --no-dev 2>/dev/null \
    || uv sync --no-install-project --no-dev

# Then copy the app source.
COPY backend/ /app/

# Install the project itself.
RUN uv sync --no-dev

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 8000

# Migrations run on container start, then the app starts. --reload-dir is given
# explicitly so the reloader watches both the app source (/app) and the mounted
# engine package (/engine); without it uvicorn only watches the working dir.
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app --reload-dir /engine"]
