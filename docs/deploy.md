# Deploy

**Status: deferred.** Phase 6 ships the deploy blueprint (`render.yaml`) but
does not flip a live deploy. To go live, follow the runbook below.

## Architecture

Render hosts everything except blob storage:

| Service          | Type        | Purpose                                  |
| ---------------- | ----------- | ---------------------------------------- |
| `vfp-postgres`   | Database    | App data + RLS                           |
| `vfp-redis`      | Redis       | arq job queue                            |
| `vfp-backend`    | Web (Docker)| FastAPI on uvicorn                       |
| `vfp-worker`     | Worker      | arq worker for SoA parse jobs            |
| `vfp-frontend`   | Static      | Vite build of `frontend/dist`            |
| **External**     | S3-compat   | Document uploads (AWS S3 or Cloudflare R2)|

The frontend rewrites `/api/*` to the backend service so cookies stay
same-origin (no CORS gymnastics in production).

## First-time deploy

1. **Provision external blob storage.** Render does not host S3; create an AWS
   S3 bucket (or Cloudflare R2) and an IAM user with `PutObject` / `GetObject`
   on the bucket only.

2. **Connect the repo.** In Render → New → Blueprint, point at this repo and
   accept the auto-detected `render.yaml`.

3. **Set secrets** on `vfp-backend` and `vfp-worker` (these are marked
   `sync: false` in the blueprint and must be entered by hand):
   - `ANTHROPIC_API_KEY` — for SoA parsing (PRD §5.4)
   - `S3_ENDPOINT_URL` — e.g. `https://s3.us-east-1.amazonaws.com` or the R2
     equivalent
   - `S3_BUCKET`
   - `S3_ACCESS_KEY_ID`
   - `S3_SECRET_ACCESS_KEY`

   `SESSION_SECRET` is generated automatically; do not set it manually.

4. **Apply the blueprint.** Render creates the database, Redis, backend,
   worker, and static frontend. The backend's `CMD` runs Alembic migrations
   on boot — first deploy creates every table + RLS policy.

5. **Create the first org** via `POST /orgs` (the signup endpoint is open;
   first user becomes Org Admin).

## Operational notes

- **RLS roles.** The backend container runs as `app_user`. Alembic runs as
  `app_owner` (BYPASSRLS). Both come from the same Render `DATABASE_URL`
  today; if Render adds per-role connection strings, split them.
- **Migrations on deploy.** `alembic upgrade head` runs on every backend
  boot. Long-running migrations should be paused-deploy: cap the migration
  in a separate release, or run it manually via the Render shell.
- **Worker scale.** One worker is fine for v1. SoA parse jobs are
  user-initiated and bursty; if the queue backs up, scale `vfp-worker`
  horizontally — arq supports many workers on one Redis queue.
- **Logs.** Render aggregates per-service. Tail with `render logs --service
  vfp-backend --tail`.
- **Backups.** Render Postgres has daily snapshots on Starter; bump the plan
  for point-in-time recovery before storing customer data.

## Pre-flight checklist (don't deploy until each is checked)

- [ ] All Phase 6 tests green (engine, backend, frontend, smoke)
- [ ] `ANTHROPIC_API_KEY` rotated since the Phase 5 dev key
- [ ] S3 bucket policy denies public reads
- [ ] CORS allowlist in `render.yaml` matches the deployed frontend URL
- [ ] First-org signup tested end-to-end against the live API
