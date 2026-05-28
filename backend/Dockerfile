FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# uv from the official distroless image — no curl/install gymnastics.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps in a separate layer for cache efficiency.
COPY backend/pyproject.toml backend/uv.lock* /tmp/backend/
RUN cd /tmp/backend && uv sync --frozen --no-install-project --no-dev 2>/dev/null \
    || (cd /tmp/backend && uv sync --no-install-project --no-dev)

# Then copy the app source.
COPY backend/ /app/

# Install the project itself.
RUN uv sync --no-dev

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 8000

# Migrations run on container start, then the app starts.
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
