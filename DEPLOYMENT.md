# DEPLOYMENT.md — Big Money DFS

Milestone 30 (Production Infrastructure Foundation) prepared this codebase for a
future hosted private beta. **This document does not deploy anything.** No
production accounts have been created, no DNS has been configured, Stripe is
not in live mode, and nothing here runs automatically. It records what a human
operator would need to do, and what still needs validating, when that decision
is actually made.

## Service topology

A hosted deployment needs four services plus DNS/HTTPS, which the host manages:

| Service | What it is | Source |
|---|---|---|
| **WEB** | Next.js dashboard (member product + admin) | `dashboard/` |
| **WORKER** | Background job worker (slate Process/Refresh pipeline) | `dashboard/scripts/run-job-worker.ts` |
| **DATABASE** | Shared PostgreSQL (membership, billing, admin, jobs) | `dashboard/lib/db/migrations-postgres/` |
| **OBJECT STORAGE** | S3-compatible bucket (research/projection/lineup artifacts) | any S3-compatible provider |
| **DNS / HTTPS** | Domain + TLS termination | host-managed, not this codebase's concern |

WEB and WORKER are the same codebase (`dashboard/`) started two different ways
— `npm run start` for WEB, `node scripts/run-job-worker.ts` for WORKER. Locally
and in a genuinely single-instance early deployment, WEB alone is sufficient:
the admin Process/Refresh routes run the job inline
(`lib/jobs/worker.ts::runOneQueuedJob`) without a separate WORKER process. A
separate WORKER only matters once WEB needs to scale horizontally or the
pipeline's runtime becomes long enough that tying it to an HTTP request's
process is undesirable.

## Environment variables

Names only — **never commit or share actual values**. Nothing in this
repository logs or returns a secret value (see `lib/billing/stripeConfig.ts`'s
own docstring for the established convention this follows).

### Dashboard (Node / Next.js)

| Variable | Required in production? | Purpose |
|---|---|---|
| `NODE_ENV` | Set by the platform | `development` / `test` / `production` — see `lib/env.ts` |
| `DATABASE_URL` | Yes (or explicit override) | PostgreSQL connection string. Missing in production → fails closed (`lib/db/backend.ts`) |
| `ALLOW_SQLITE_IN_PRODUCTION` | No | Explicit escape hatch to allow local SQLite in production anyway |
| `OBJECT_STORAGE_ENDPOINT` | No (omit for real AWS S3) | S3-compatible endpoint URL (R2/B2/MinIO/etc.) |
| `OBJECT_STORAGE_REGION` | Yes (or explicit override) | Bucket region |
| `OBJECT_STORAGE_BUCKET` | Yes (or explicit override) | Bucket name |
| `OBJECT_STORAGE_ACCESS_KEY` | Yes (or explicit override) | S3 access key id |
| `OBJECT_STORAGE_SECRET_KEY` | Yes (or explicit override) | S3 secret access key |
| `ALLOW_LOCAL_STORAGE_IN_PRODUCTION` | No | Explicit escape hatch to allow local-disk artifact storage in production anyway |
| `PRIVATE_BETA` | No | `true` restricts the member product to ADMIN + beta-approved users (`lib/auth/betaAccess.ts`) |
| `WORKER_ID` | No | Identifies a standalone worker process in `worker_heartbeats` (defaults to `worker-<pid>`) |
| `JOB_WORKER_POLL_INTERVAL_MS` | No | Standalone worker poll interval (default 5000) |
| `BIGMONEY_DB_PATH` | No | Local SQLite file path override (dev only) |
| `MLB_DFS_ROOT` | No | Artifact root override |
| `MLB_DFS_RUNSTATE_DIR` | No | Orchestrator run-state directory override |
| `MLB_DFS_PYTHON` | No | Python interpreter override for spawned pipeline scripts |
| `ADMIN_BOOTSTRAP_EMAIL` | No | One-time admin bootstrap |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_WEEKLY_PRICE_ID` / `STRIPE_MONTHLY_PRICE_ID` | For billing | Test-mode only is currently enforced (`lib/billing/stripeConfig.ts`) |

### Python pipeline (research/, scripts/)

| Variable | Purpose |
|---|---|
| `DFS_SALARY_PROVIDER` / `DFS_PROVIDER_API_KEY` | DK salary provider config |
| `EXTERNAL_PROJECTION_PROVIDER` | External projection baseline provider |
| `GAME_ENVIRONMENT_PROVIDER` / `GAME_ENVIRONMENT_UMPIRE_PROVIDER` | Weather/Vegas/umpire providers |
| `SPORTSGAMEODDS_API_KEY` / `THE_ODDS_API_KEY` | Vegas odds providers |
| `OBJECT_STORAGE_ENDPOINT` / `_REGION` / `_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` | Same five vars as the dashboard, for `research/artifact_storage.py::S3ArtifactStorage` |

Python entry points auto-load `dashboard/.env.local` if present
(`config/env_loader.py`) so one local file configures both sides in
development; a hosted deployment sets these directly in the WORKER service's
real environment instead.

## Database

- **Development / test**: local SQLite (`dashboard/data/bigmoney.db`), zero
  configuration.
- **Production**: PostgreSQL, `DATABASE_URL` required. Migrations live in
  `dashboard/lib/db/migrations-postgres/` (ported from the SQLite originals in
  `dashboard/lib/db/migrations/` — see those files' own comments for the few
  dialect differences: `COLLATE NOCASE` → a case-insensitive index,
  `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`, SQLite's table-rebuild
  workaround → native `ALTER TABLE ... DROP/ADD CONSTRAINT`).
- **Migration tool**: `dashboard/scripts/migrate-sqlite-to-postgres.ts` — a
  local admin/developer CLI, dry-run by default (`--execute` to actually
  write), row-count validated after each table, refuses to overwrite a
  non-empty target table, and never prints a password hash, session/
  verification/reset token hash, or Stripe customer id (redacted in every
  report).

### Known remaining gap — be honest about this

`dashboard/lib/db/client.ts::getDb()` and the 17 query modules under
`dashboard/lib/db/*.ts` (users, sessions, subscriptions, entitlements,
audit log, slate status, jobs, etc.) are **SQLite-only**. When `DATABASE_URL`
is configured, `getDb()` deliberately throws a clear error rather than
silently using local SQLite or silently pretending to support Postgres. A
real production Postgres deployment needs those 17 modules ported to the
async `lib/db/postgresClient.ts` adapter — that port is real, separate work
this milestone did not attempt (the scope here was the connection/migration
layer and an honest, fail-closed selection mechanism, not a rewrite of every
existing query call site).

## Object storage

- **Development**: local disk, `LocalStorageBackend` (`dashboard/lib/storage/StorageBackend.ts`) / `LocalArtifactStorage` (`research/artifact_storage.py`).
- **Production**: any S3-compatible provider (AWS S3, Cloudflare R2, Backblaze
  B2, MinIO, ...) via `ProductionObjectStorageBackend` (Node,
  `@aws-sdk/client-s3`) and `S3ArtifactStorage` (Python, `boto3`). Both are
  real, tested implementations (mocked S3 client in unit tests — no cloud
  resources required to run the test suite).
- Neither the dashboard's loaders (`lib/loaders.ts`, `lib/discovery.ts`) nor
  most of the Python persistence modules are wired to read/write through
  these abstractions yet — `research/storage.py::save_json()` (the shared
  primitive underneath `dfs/persistence.py`, `ownership/persistence.py`,
  `native_projections/persistence.py`, and others) now routes through
  `LocalArtifactStorage` internally, which is the centralization point; a
  full swap to `S3ArtifactStorage` for every writer, and swapping every
  dashboard loader to `StorageBackend`, is real, separate follow-up work.

## Background jobs

- `jobs` table (`dashboard/lib/db/migrations/0005_production_infrastructure.sql`):
  `PROCESS_SLATE` and `REFRESH_SLATE` are implemented end to end
  (`dashboard/lib/jobs/slateJobHandlers.ts`, wired into
  `app/api/admin/slates/process/route.ts` and `.../refresh/route.ts`).
  `BUILD_LINEUPS`, `RESULTS_COLLECTION`, `MODEL_EVALUATION` are valid job
  types (the CHECK constraint already allows them) with no handler yet —
  claiming one fails clearly (`NO_HANDLER`) rather than silently succeeding.
- Idempotent: a partial unique index (`idx_jobs_active_uniqueness`) prevents
  two QUEUED/RUNNING jobs for the same `(slate_date, slate_id, job_type)`.
- Bounded retry: only `TransientJobError` (an explicit, positive signal from
  a handler) is retried, up to `max_attempts` (default 3). A plain thrown
  error — a validation failure, a model error — is never blindly retried.
- **Inline execution** (default, no separate WORKER needed): the admin routes
  call `lib/jobs/worker.ts::runOneQueuedJob` directly after enqueueing.
- **Standalone worker** (`scripts/run-job-worker.ts`): a poll loop claiming
  from the same `jobs` table, for a deployment that actually splits WEB and
  WORKER into separate services. Exercised as a standalone process against
  local SQLite during this milestone; **not validated against a real
  multi-process/multi-machine Postgres deployment** — `claimNextQueuedJob`'s
  own docstring notes that genuine multi-worker concurrency safety would need
  row-level locking (`FOR UPDATE SKIP LOCKED` or equivalent), not yet added.
- Worker liveness (`worker_heartbeats` table) is derived entirely from a
  timestamp, never in-process memory — ONLINE (≤30s), STALE (≤2min), OFFLINE
  beyond that (`dashboard/lib/jobs/heartbeat.ts`).

## Health and readiness

- `GET /api/health` — public, unauthenticated, minimal
  (`status`/`version`/`timestamp` only, nothing about infrastructure).
- Admin System page (`/admin/system`) — SAFE-only readiness (no secret
  values): Database (CONNECTED/ERROR + SQLite/PostgreSQL), Object Storage
  (CONNECTED/NOT CONFIGURED/ERROR), Job Queue (CONNECTED/ERROR + queued/
  running counts), Worker (ONLINE/OFFLINE), plus the existing SportsGameOdds
  and Stripe status cards.

## Structured logging & error monitoring

- `dashboard/lib/logger.ts` — one JSON line per event
  (`timestamp`/`level`/`message` + `requestId`/`jobId`/`slateId`/`slateDate`/
  `operation`/`durationMs`/`status` where applicable). Any field whose name
  looks secret-shaped (password/token/secret/api key/authorization/cookie/
  credential) is redacted before printing, regardless of caller intent.
- `dashboard/lib/errorMonitoring.ts` — `captureError()` is a clean, minimal
  seam for a future hosted error-monitoring vendor (Sentry, Bugsnag, etc.).
  **No vendor is chosen or paid for** — it currently just logs via
  `logger.ts`; wiring a real SDK later is a one-function change.
- Currently wired into the job worker (`lib/jobs/worker.ts`) as the clearest,
  highest-value integration point. Not yet wired into every request handler
  — a deliberate scope boundary, not an oversight.

## Private beta

`PRIVATE_BETA=true` restricts the member product (`/dashboard/*`) to ADMIN +
users with `users.beta_access_granted_at` set. It is an account-level access
gate in front of the product, **not** a replacement for the subscription/
entitlement system — nothing about `entitlements`/`user_entitlements` is
touched. Admin grants/revokes it from a user's detail page
(`/admin/users/[id]`, "Approve Beta Access" / "Remove Beta Access"), and
`/admin/users` has a Beta Access filter. Every grant/revoke is audit-logged.

## Local development

Unaffected by any of this milestone's guards: no `DATABASE_URL` → SQLite; no
`OBJECT_STORAGE_*` → local disk; no separate WORKER process needed; no
`PRIVATE_BETA` → every authenticated user has access, exactly as before. No
cloud service or account is required to run `npm run dev`, `npm run test`, or
`python -m pytest tests/`.

## What "DO NOT DEPLOY" means here

This milestone prepared the codebase. It did **not**:
- Create any production PostgreSQL database, object storage bucket, or
  hosting account.
- Change any DNS record.
- Enable Stripe live mode (test-mode-only enforcement is unchanged and still
  active — `isLiveSecretKey()` in `lib/billing/stripeConfig.ts` still blocks
  a live key).
- Set up automatic deployment (CI/CD) of any kind.

## Resource footprint — measured, not invented

No prior "M28 performance stage" measurements exist in this repository (no
distinguishable commit history predates a single squashed initial commit, and
no memory files or scripts reference such data) — this section states real,
measured-in-this-environment numbers where obtaining them was practical, and
says "not measured" rather than inventing a number everywhere else.

**Measured — accumulated local artifact storage** (`du -sh`, this
development environment; several days of dev/test slate data, not one
slate):

| Directory | Size |
|---|---|
| `dfs_input/` | 38M |
| `ownership_predictions/` | 7.2M |
| `native_projection_snapshots/` | 3.4M |
| `ai_projection_snapshots/` | 3.2M |
| `research_output/` | 1.9M |
| `game_environment_snapshots/` | 1.8M |
| `results/` | 52K |

**Measured — test suite scale**: 1,613 Python tests (`python -m pytest
tests/`, ~19s uncontended on this machine); dashboard test file/case counts
below (Testing & Verification section).

**Not measured** (would require a real hosted deployment to observe honestly,
not fabricated here): WEB process steady-state memory under real member
traffic, WORKER process CPU/memory during a real slate pipeline run, database
connection/query volume under concurrent members, and network egress from
object storage reads. A first hosted deployment should capture these via the
platform's own metrics before sizing a paid tier.

## Dependencies added this milestone

Node (`dashboard/package.json`): `pg` (PostgreSQL client), `@aws-sdk/client-s3`
(S3-compatible object storage), `@types/pg` (dev). Python: `boto3` (S3-
compatible object storage) — installed locally for this milestone's
development; **no project-wide `requirements.txt` exists in this repository**
(confirmed absent before this milestone too), so this is not otherwise
tracked in a manifest — a gap that predates this milestone, noted here rather
than silently worked around by inventing one outside this milestone's scope.
