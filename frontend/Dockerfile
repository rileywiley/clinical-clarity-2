FROM node:20-slim AS base

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH"

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml* /app/
RUN pnpm install --frozen-lockfile 2>/dev/null || pnpm install

COPY frontend/ /app/

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]
