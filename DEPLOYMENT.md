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
— `npm run start` for WEB, `npm run worker` for WORKER. Locally
and in a genuinely single-instance early deployment, WEB alone is sufficient:
the admin Process/Refresh routes run the job inline
(`lib/jobs/worker.ts::runOneQueuedJob`) without a separate WORKER process. A
separate WORKER only matters once WEB needs to scale horizontally or the
pipeline's runtime becomes long enough that tying it to an HTTP request's
process is undesirable.

## Production deployment validation (Milestone 33.4)

Final local pre-deployment audit before creating any real hosting
infrastructure. **Nothing was deployed, purchased, or provisioned as
part of this milestone.**

### WEB / WORKER / POSTGRES / OBJECT STORAGE division of responsibility

| Service | Owns | Source |
|---|---|---|
| **WEB** | Next.js dashboard: auth/sessions, memberships/entitlements/Stripe, admin UI, optimizer UI, projection pages, all API routes. Spawns Python as a subprocess for slate Process/Refresh when no separate WORKER is running. | `dashboard/app/`, `dashboard/lib/` |
| **WORKER** | Standalone poll loop claiming the SAME `jobs` table WEB's inline execution also uses -- slate refresh pipeline, research collection, player identity, Native/AI/ML/BlueCollar projections, ownership, weather, Vegas, all via the identical `lib/slatePipeline.ts::runSlatePipeline()` WEB uses inline. No optimizer-build job type exists yet (optimizer builds are synchronous, member-request-triggered, not queued). | `dashboard/scripts/run-job-worker.ts` |
| **POSTGRES** | `users`, `sessions`, `password_reset_tokens`, `subscriptions`, `entitlements`/`user_entitlements`, `feature_flags`, `jobs`, `worker_heartbeats`, `slate_status`, `slate_publish_history`, `admin_audit_log`, Stripe webhook event log. | `dashboard/lib/db/migrations-postgres/` |
| **OBJECT STORAGE** | Every artifact-storage-routed Python writer (research packages, pitcher/batter board snapshots, DK pool/match-report snapshots, player identity crosswalk, ownership, Native/AI/ML/BlueCollar/FantasyPros projections, game environment, lineup sets) plus model artifacts (fetched + cached locally on first use, never the source of truth). | `research/artifact_storage.py` (Python writers), `dashboard/lib/storage/StorageBackend.ts` (Node readers) |

### Remaining local-disk (C:\ / any single machine) dependencies

Audited every `process.env`/local-path reference across the app. Three
found, all either already-accepted single-instance escape hatches or a
genuinely pre-existing, honestly-documented limitation -- none newly
introduced by this milestone:

1. **`BIGMONEY_DB_PATH` / SQLite** — dev-only; production fails closed
   without `DATABASE_URL` (see "Production startup safety" below). Not a
   real concern.
2. **Model artifact local cache** (`historical_models/pitcher_v1/persistence.py::load_model`)
   — by design (Milestone 33.2 Part 7): each process caches the model
   file to ITS OWN local disk after the first fetch from object storage.
   This is intentional, not a gap -- object storage remains the source
   of truth, and every process (WEB or WORKER, however many instances)
   independently self-heals from it on a cold start.
3. **`/api/refresh`'s run-state IS genuinely per-process** —
   `lib/orchestrator/runner.ts` (a pre-Milestone-29 "one-click refresh"
   mechanism, distinct from and older than the job-queue-backed
   `/api/admin/slates/{process,refresh,discover}` routes this project's
   more recent milestones use) keeps its `activeRun`/`lastCompletedRun`
   state **in-memory, with a local-disk copy purely for crash-visibility
   debugging** — its own top-of-file comment says exactly this. It is
   **not** a dead/legacy code path: `components/TopNavigation.tsx` and
   `components/MissingDataState.tsx` both still call it, and it is
   admin-gated but reachable from general UI chrome, not confined to
   `/admin/slates`. On a single WEB instance this is completely correct
   (matches its own documented design). **On more than one WEB instance,
   a status poll landing on a different instance than the one that
   started the run would see stale/empty state** — a real, confirmed
   architectural gap, not a hypothetical one. Out of scope to fix here
   per this milestone's explicit "do not redesign working MLB features"
   boundary; the existing, newer job-queue mechanism (`lib/jobs/queue.ts`,
   already Postgres-backed and already correctly shared across
   instances) is the natural target for a future migration. **Practical
   implication: WEB must stay single-instance until that migration
   happens** — see "Recommended M33.5 scope" in this milestone's final
   report.

### Production environment variable inventory

Names and configuration status only — **no real values printed, ever**.
Confirmed live: `dashboard/.env.local` is `.gitignore`d (`dashboard/.gitignore`'s
`.env*` pattern) and was never committed (`git log` on it is empty).

| Variable | Class | Notes |
|---|---|---|
| `DATABASE_URL` | **REQUIRED**, **SECRET** | Fails closed without it in production (`ALLOW_SQLITE_IN_PRODUCTION` is the loud, explicit override). |
| `OBJECT_STORAGE_REGION` / `_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` | **REQUIRED**, **SECRET** | Fails closed without all four (`ALLOW_LOCAL_STORAGE_IN_PRODUCTION` is the override). Same 4 names on both Node and Python sides. |
| `OBJECT_STORAGE_ENDPOINT` | OPTIONAL | Omit for real AWS S3; required for R2/other S3-compatible providers. |
| `DFS_SALARY_PROVIDER=draftkings_unofficial` + `DK_UNOFFICIAL_ENABLED=true` | **REQUIRED** | DraftKings Unofficial is the permanent live DK slate source (Milestone 33.2.1) — without BOTH set, zero slates are ever discovered. Not secret (no value beyond a fixed string), but required. |
| `BLUECOLLAR_API_KEY` | OPTIONAL, **SECRET** | Degrades to "not configured" gracefully if absent (BlueCollar is an optional, admin-gated projection source). |
| `FANTASYPROS_API_KEY` | OPTIONAL, **SECRET** | Same graceful-degradation pattern. |
| `SPORTSGAMEODDS_API_KEY` / `THE_ODDS_API_KEY` | OPTIONAL, **SECRET** | Vegas odds provider(s); degrades to "not connected" if absent. |
| `FANTASYDATA_API_KEY` | **DEVELOPMENT ONLY**, **SECRET** | `fantasydata_audit/` is an isolated, one-off audit client — confirmed NOT wired into any production pipeline (Native/AI/FantasyPros/Vegas/Ownership/Optimizer). Do not configure in production. |
| `GAME_ENVIRONMENT_PROVIDER` / `GAME_ENVIRONMENT_UMPIRE_PROVIDER` / `EXTERNAL_PROJECTION_PROVIDER` | OPTIONAL | Provider-selection overrides; sensible defaults apply when unset. |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | OPTIONAL for this deployment phase, **SECRET** | Required once billing goes live; test-mode-only enforcement (`isLiveSecretKey()`) stays active regardless. |
| `STRIPE_WEEKLY_PRICE_ID` / `STRIPE_MONTHLY_PRICE_ID` | OPTIONAL for this deployment phase | Same as above. |
| `ADMIN_BOOTSTRAP_EMAIL` | OPTIONAL | Has a hardcoded fallback; set explicitly for a real deployment rather than relying on the default. |
| `PRIVATE_BETA` | OPTIONAL | Member-product access gate; unset means open to every authenticated user. |
| `ALLOW_SQLITE_IN_PRODUCTION` / `ALLOW_LOCAL_STORAGE_IN_PRODUCTION` | OPTIONAL escape hatches | Must stay **unset** in a real multi-instance production deployment — see "Production startup safety". |
| `WORKER_ID` | OPTIONAL | Defaults to `worker-<pid>`. |
| `JOB_WORKER_POLL_INTERVAL_MS` | OPTIONAL | Defaults to 5000. |
| `MLB_DFS_PYTHON` | OPTIONAL | Defaults to bare `python` on PATH. |
| `MLB_DFS_ROOT` | OPTIONAL | Defaults to the parent of `dashboard/`; a Docker image built from this repo's own layout never needs to set this. |
| `MLB_DFS_RUNSTATE_DIR` | OPTIONAL, DEVELOPMENT-LEANING | Local-disk debug-visibility copy for `/api/refresh`'s run state — see the "remaining local-disk dependencies" note above. |
| `TEST_DATABASE_URL` | **DEVELOPMENT/TEST ONLY** | Gates the real-Postgres integration test suite; never set in production. |
| `DFS_PROVIDER_API_KEY` | **DEVELOPMENT/TEST ONLY**, **SECRET** | Generic override key for an explicit non-default `DFS_SALARY_PROVIDER`; unused by the permanent `draftkings_unofficial` provider. |
| `NODE_ENV` | **REQUIRED** (platform-set) | Drives every fail-closed check in this document; a real hosting platform sets this automatically. |

No `NEXT_PUBLIC_*` variable exists anywhere in the codebase — confirmed
by grep — so no storage/database credential can reach the browser bundle
even by naming mistake.

### Production startup safety

All confirmed by direct code audit of the exact fail-closed logic (Milestone 30/33.1/33.2's `resolveDbBackend()`/`resolveStorageBackend()`), re-verified live via the existing, passing test suites (`lib/db/__tests__/backend.test.ts`, `lib/storage/__tests__/backend.test.ts`):

- **Cannot silently use SQLite in production**: `resolveDbBackend()` throws `ProductionDatabaseNotConfiguredError` when `NODE_ENV=production` and `DATABASE_URL` is unset, unless `ALLOW_SQLITE_IN_PRODUCTION=true` is explicitly set. The error message names the exact variables to set — no credential value.
- **Cannot silently use local artifact storage in production**: identical pattern, `resolveStorageBackend()` (Node) / `resolve_artifact_storage()` (Python), `ProductionStorageNotConfiguredError` / `ProductionStorageNotConfiguredError`, `ALLOW_LOCAL_STORAGE_IN_PRODUCTION` override.
- **A malformed `DATABASE_URL` cannot fall back to SQLite**: `resolveDbBackend()`'s only check is "is `DATABASE_URL` a non-empty string" — there is no format-validation step that could reject a malformed value and fall through to a different branch. Once any non-empty string is present, the Postgres path is chosen unconditionally; a malformed value fails loudly downstream (a real `pg` connection/query error, surfaced through `/api/health` as `database: unhealthy` and a `503`), never a silent SQLite substitution. (Not additionally live-tested against a fresh process this milestone, to avoid disrupting the already-running dev server instance being used for the rest of this validation — the code-path guarantee itself has no conditional branch that could produce a different result.)
- **Broken object storage cannot fall back to local disk**: same reasoning — `resolveStorageBackend()`/`resolve_artifact_storage()` pick object storage unconditionally once configured; a broken bucket/credential fails loudly (a real S3 error), surfaced through `/api/health` as `storage: unhealthy`.
- **WEB and WORKER use the same Postgres database and the same object-storage namespace by construction**: both read the identical `DATABASE_URL` / `OBJECT_STORAGE_*` variable names from their process environment — there is no separate, WORKER-specific connection configuration anywhere in the codebase to drift out of sync.
- **No credential ever appears in an error message**: confirmed by reading every thrown-error string in `resolveDbBackend()`/`resolveStorageBackend()`/`resolve_artifact_storage()`/`getDatabaseReadiness()`/`getObjectStorageReadiness()` — every one names only variable NAMES, backend kinds, or generic connection-failure text, never a value.

### Worker validation

Existing test coverage (all currently passing) already exercises every
required behavior — re-run as part of this milestone's verification,
not newly written, since it already covers this exhaustively:

- **Claims jobs**: `lib/jobs/__tests__/queue.test.ts`, `jobQueueConcurrency.test.ts` (+ a real-Postgres-gated `jobQueueConcurrency.postgres.test.ts`, `TEST_DATABASE_URL`-gated).
- **Executes the slate pipeline / persists through shared storage / updates job status**: `lib/jobs/__tests__/worker.test.ts` ("claims a job, runs its registered handler, and marks it SUCCEEDED"), exercising the exact `runSlatePipeline()` path both WEB-inline and WORKER-standalone execution share.
- **Survives a failed job without crashing permanently**: `worker.test.ts`'s "marks the job FAILED (not retryable by default) when the handler throws" and "does not throw synchronously even when the handler rejects" — a thrown/rejected handler is caught, recorded, and the poll loop keeps running.
- **Standalone startup itself**: previously **unverified** — see "Node" under Runtime & build reproducibility above for the real `ERR_MODULE_NOT_FOUND` startup bug this milestone found and fixed. Live-confirmed post-fix: `npm run worker` starts and begins polling.
- No repeated live paid-API calls were made for this validation — job-queue tests use the project's existing fixture/mock pattern (`__setPythonRunnerForTests`), matching every other test in this codebase.

### Ephemeral-storage audit

| Data | Source of truth | Notes |
|---|---|---|
| Users, sessions, password resets | **POSTGRES** | |
| Subscriptions, entitlements, feature flags | **POSTGRES** | |
| Slate status, publish history, jobs, worker heartbeats, admin audit log | **POSTGRES** | |
| Research packages, pitcher/batter board snapshots | **OBJECT STORAGE** | Python-written via `research/artifact_storage.py`. |
| DK player pool / match report snapshots | **OBJECT STORAGE** | |
| Player identity crosswalk | **OBJECT STORAGE** | Immutable versioned snapshots (Milestone 33.2 Part 9). |
| Native / AI / Big Money ML projection snapshots | **OBJECT STORAGE** | |
| BlueCollar / FantasyPros projection snapshots | **OBJECT STORAGE** | |
| Weather / Vegas (game environment) snapshots | **OBJECT STORAGE** | |
| Ownership snapshots | **OBJECT STORAGE** | |
| Optimizer lineup-set results | **OBJECT STORAGE** | |
| Big Money Pitcher/Hitter Model V1 artifacts | **OBJECT STORAGE** (source of truth) + per-process local cache | Never the image; see "Model artifact packaging". Confirmed fetchable from a cold cache — Part 7 below. |
| Historical training warehouse | **N/A — intentionally never in production** | Offline-only; confirmed by import audit that no production code path touches it. |
| `/api/refresh`'s in-flight run status | **EPHEMERAL** (by original design, single-instance-only) | See "Remaining local-disk dependencies" above — the one confirmed gap, not a blocker for a single WEB instance, a real constraint once WEB scales horizontally. |

**No POSTGRES/OBJECT-STORAGE-classified item was found EPHEMERAL. The one EPHEMERAL item found (`/api/refresh` run status) is a pre-existing, by-design, single-process mechanism, not silently-broken state — flagged honestly rather than mis-classified as safe.**

### Deployment configuration (portable, vendor-neutral)

```
PUBLIC INTERNET
      |
      v
WEB SERVICE (npm run start)
      |
      +------ POSTGRESQL (DATABASE_URL -- any standard Postgres)
      |
      +------ OBJECT STORAGE (OBJECT_STORAGE_* -- any S3-compatible endpoint)
      |
      v
JOB QUEUE (the `jobs` Postgres table)
      |
      v
WORKER SERVICE (npm run worker)
      |
      +------ POSTGRESQL (same DATABASE_URL)
      |
      +------ OBJECT STORAGE (same OBJECT_STORAGE_* namespace)
      |
      +------ External APIs (DraftKings Unofficial, SportsGameOdds, FantasyPros, BlueCollar, MLB Stats)
```

No hosting vendor is hardcoded anywhere in the codebase — `DATABASE_URL`
is a standard Postgres connection string (works against any managed
Postgres), `OBJECT_STORAGE_*` targets any S3-compatible endpoint via a
configurable `OBJECT_STORAGE_ENDPOINT` (Cloudflare R2, AWS S3, Backblaze
B2, MinIO, ...), and both WEB/WORKER are plain Node processes runnable
on Railway, Vercel (WEB only — Vercel does not run long-lived background
processes, so WORKER would need a different host if used), a plain VM,
or the Docker image this milestone added.

## Runtime & build reproducibility (Milestone 33.3)

Goal: a fresh Linux host/container can build and run this codebase
identically to local dev, with every version pinned rather than
whatever happened to be installed on a developer's machine. **Not
deployed anywhere as part of this milestone** — see "What 'DO NOT
DEPLOY' means here" below.

### Python

- **Version**: `.python-version` pins `3.13.7` — this is not an
  arbitrary "latest" choice: `data/models/mlb/{hitter,pitcher}/v1/metadata.json`
  already records that the trained models were built with exactly
  Python 3.13.7 / scikit-learn 1.9.0 / pandas 3.0.5 / numpy 2.5.2.
  scikit-learn's own pickle/joblib compatibility is not guaranteed
  across version changes, so matching exactly (not "3.13-compatible")
  is the safe choice.
- **Dependency manifest**: `requirements.txt` (production) +
  `requirements-dev.txt` (adds `pytest` only). Neither existed before
  this milestone — the project previously ran off whatever was already
  installed on a developer's machine, with no manifest at all. Every
  package listed was confirmed, by auditing every real `import`
  statement across the actual application code (not this machine's
  broader installed-package set), to be genuinely used — several
  packages that happened to be installed locally (`requests`,
  `beautifulsoup4`, `lxml`, `pybaseball`, `matplotlib`, `PyGithub`,
  `PyJWT`, `PyNaCl`, `cryptography`) are confirmed **unused** by this
  codebase (it uses stdlib `urllib.request` for HTTP, not `requests`)
  and are deliberately excluded to keep the production dependency
  surface minimal.
- **Versions are pinned exactly (`==`)**, not `>=`/range — see
  `requirements.txt`'s own docstring. Not pip-compile/poetry-locked
  (no transitive-dependency hashes) — a real next step (see "Recommended
  M33.4 scope" in this milestone's final report), not done here.
- **PyArrow**: confirmed a genuine **production** dependency, not just
  offline-training — `player_identity/historical_backfill.py`'s
  `pd.read_parquet()` is called from `player_identity/refresh.py`, which
  runs on every live slate Process/Refresh, even though the historical
  warehouse itself stays out of normal production runtime (Part 8
  below).
- **Historical warehouse in production**: **not required, and must not
  run there.** `historical_mlb/` (warehouse building) and
  `historical_models/*/train.py` (model training) are offline-only,
  never invoked by any live request/pipeline path — confirmed by the
  same audit above (no production code path imports them). The trained
  MODEL ARTIFACTS they produce ARE needed in production (see below);
  the multi-gigabyte warehouse data that produced them is not.
- **Clean-environment validation performed**: a fresh virtualenv
  (`python -m venv`, no access to this machine's other installed
  packages) with `pip install -r requirements.txt` only, then
  `python scripts/smoke_test_runtime.py` — every check passed (package
  imports, real model load + inference, a real OR-Tools CP-SAT solve,
  storage abstraction resolution). See that script's own docstring; it
  never touches a real network and is safe to re-run anywhere, including
  as a container startup/readiness gate.

### Node

- **Version**: `.nvmrc` pins `24.19.0`; `dashboard/package.json`'s
  `engines.node` requires `>=23.6.0`. `node:sqlite` (local dev's
  database) needs 22.5+; the stricter floor here is for Node's own
  native TypeScript type-stripping, unflagged (on by default) starting
  at Node 23.6, used by the `tsx` runtime below.
- **`scripts/run-job-worker.ts` and `scripts/migrate-postgres-schema.ts`
  run via `tsx`** (`npm run worker`, `npm run db:migrate:postgres`), not
  plain `node`. Milestone 33.4 finding: `scripts/run-job-worker.ts`
  itself uses explicit `.ts` import extensions, but transitively imports
  `lib/slatePipeline` (and, through it, most of `lib/`) using this
  codebase's normal EXTENSIONLESS import style — the style every
  internal import in this project already uses, since Next.js's own
  bundler resolves it fine. Node's *native* ESM loader does not resolve
  extensionless specifiers, so a real `node scripts/run-job-worker.ts`
  invocation crashed immediately with `ERR_MODULE_NOT_FOUND` on
  `lib/slatePipeline` — confirmed live, a genuine production blocker,
  not a hypothetical one. `scripts/migrate-postgres-schema.ts` happened
  to exit before reaching an extensionless import in local testing (no
  `DATABASE_URL` set → early return) — this masked the exact same
  latent problem in that script, which was not actually verified in
  Milestone 33.3 despite that milestone's report saying it was
  confirmed clean. `tsx` (esbuild-based) resolves extensionless
  TypeScript imports exactly like Next.js does, so this fixes both
  scripts with a one-line invocation change each and zero source-file
  changes across the ~100+ files either script transitively imports.
  Pinned as an exact production dependency (`tsx==4.23.12` in
  `package.json`, not just a dev tool) since the WORKER and migration
  commands need it at runtime, not just in development. Confirmed live:
  both `npm run worker` (starts and begins polling, no crash) and
  `npm run db:migrate:postgres` (same expected safety message as
  before, now with zero warnings) work correctly.
- **Dependency manifest**: `dashboard/package-lock.json` already existed
  and is already git-tracked (since Milestone 30) — `npm ci` is already
  fully reproducible; nothing new needed here.

### Linux / container compatibility audit

- **`child_process.spawn`** (`lib/orchestrator/pythonRunner.ts`, the
  ONLY subprocess-spawning call site in the app): already
  platform-neutral before this milestone — `shell: false` (no shell
  syntax interpretation on either platform), the Python executable
  resolves via `MLB_DFS_PYTHON` env override or a bare `"python"` on
  PATH (no hardcoded Windows path), `windowsHide: true` is a
  Windows-only option that Linux simply ignores. No code change needed;
  confirmed correct by static audit, not assumed.
- **No other Windows-specific assumptions found**: audited every
  `child_process`/`spawn`/`exec` call site in `dashboard/` (there is
  exactly one — pythonRunner.ts above) and grepped for hardcoded
  backslash paths, `.exe` extensions, and Windows-only commands in
  application code (as opposed to this session's own throwaway
  diagnostic scripts, which are not part of the app and were deleted).
  None found.
- **`node:sqlite`**: a Node built-in (compiled into Node itself), not a
  native npm addon requiring separate platform-specific compilation —
  no Linux-specific concern.

### Docker / container strategy

- **`Dockerfile`** (repo root, multi-stage): ONE image serves both WEB
  and WORKER (same codebase, different start command — see below), not
  two separate images. Two runtimes are required in the same final
  image: Node (Next.js) and Python (spawned as a subprocess by the
  running Node process, a genuine runtime dependency, not just a build
  tool). The exact pinned Python (`python:3.13-slim`) is copied into a
  `node:24-slim` base via a multi-stage `COPY --from=` (Debian's own apt
  repos do not reliably offer this exact CPython minor version).
- **`.dockerignore`** (repo root): excludes `.git/`, all generated
  pipeline artifact directories (mirrors `.gitignore`'s own reasoning),
  the local SQLite dev database, `node_modules`/`.next` (rebuilt inside
  the image, never copied in stale), and — deliberately — the historical
  warehouse and `data/models/` (model artifacts are fetched from object
  storage and cached locally on first use, Milestone 33.2 Part 7; baking
  them into the image would silently reintroduce the exact
  local-disk-only assumption that milestone removed), and all `.env*`
  files.
- **NOT built or pushed.** Docker was not available in the environment
  this milestone was developed in (confirmed: `docker` is not on PATH).
  Every path/command the Dockerfile relies on was instead validated via
  the equivalent plain shell commands this environment CAN run (the
  clean-venv Python validation above; `npm ci`/`npm run build` already
  exercised routinely by this project's own CI-equivalent checks). The
  Dockerfile itself has **not** been through a real `docker build` and
  should be treated as reviewed-but-unverified until one is run.

### Model artifact packaging

Unchanged from Milestone 33.2's decision, re-confirmed here: object
storage is the source of truth, fetched and cached to local disk once
per process on first use (`historical_models/pitcher_v1/persistence.py::load_model`,
reused by `hitter_v1` and `big_money_ml`). Never baked into the Docker
image or git-committed (`data/models/` stays `.gitignore`d and
`.dockerignore`d) — training happens offline, deploying a new model
version means uploading it to the bucket (see the Object Storage
section's "Production seeding inventory" table), not rebuilding the
image.

### Explicit start commands

| Command | Purpose |
|---|---|
| `npm run start` (from `dashboard/`) | **WEB** — the Next.js server. Requires `npm run build` to have already run. |
| `npm run worker` (from `dashboard/`) | **WORKER** — standalone job-queue poll loop. Optional; see Service topology above for when it's actually needed. Runs via `tsx`, not plain `node` — see "Node" above for why. |
| `DATABASE_URL=postgres://... npm run db:migrate:postgres` (from `dashboard/`) | **Migration** — applies pending Postgres schema migrations. Never automatic; see `lib/db/executor.ts`'s own docstring. |
| `python scripts/smoke_test_runtime.py` (from the repo root) | **Startup/readiness validation** — confirms the Python runtime itself is sound before serving real traffic; safe to run as a container health-check/init step. |
| `GET /api/health` | **Startup/readiness validation** — the Node-side counterpart (Milestone 33.2.2): publicly reachable, no auth required, reports sanitized database/storage health, `503` when a dependency is unhealthy. |

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
- **Production migration command** (Milestone 33.1, invocation corrected
  in 33.4 — see "Node" under "Runtime & build reproducibility" for why):
  `DATABASE_URL=postgres://... npm run db:migrate:postgres` —
  applies every not-yet-applied `dashboard/lib/db/migrations-postgres/*.sql`
  file, schema only, never touches data. Safe to run repeatedly (already
  -applied migrations are skipped). This is the one command to run before
  a production Postgres database serves its first request, and again after
  any later release that ships a new migration file. Deliberately never
  run implicitly (no auto-migrate on app startup) — see
  `lib/db/executor.ts`'s own docstring.

### Milestone 33.1 — the SQLite-only query-layer gap is closed

The gap this document used to describe here (`lib/db/client.ts::getDb()`
and the query modules under `lib/db/*.ts` being SQLite-only) is resolved.
Every query module now calls `lib/db/executor.ts::getExecutor()` instead
of `getDb()` directly — a single, backend-neutral `SqlExecutor` interface
(`lib/db/sqlExecutor.ts`) with two implementations: `SqliteExecutor`
(wraps `node:sqlite`, unchanged local-dev behavior) and `PostgresExecutor`
(wraps `pg`, real async queries, real transactions via a checked-out
`PoolClient`). `lib/db/client.ts::getDb()` itself is untouched and still
SQLite-only by design — it's now purely `SqliteExecutor`'s internal
implementation detail, never called directly by a query module.

Two tables (`subscriptions`, `stripe_webhook_events`) relied on SQLite's
built-in `rowid` for "most recently inserted" ordering, which has no
Postgres equivalent; a new migration
(`migrations-postgres/0009_ordering_sequence_columns.sql`, Postgres-only —
SQLite already has `rowid` natively) added a real `seq BIGSERIAL` column
to each. `claimNextQueuedJob()`'s Postgres path now uses
`UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`,
a single atomic statement safe under real multi-worker concurrency —
previously a documented, honest SQLite-only limitation.

**Remaining, deliberately out-of-scope items**: all timestamp columns
stay ISO-8601 TEXT on both backends (not `TIMESTAMPTZ`) — the existing
schema's own documented convention (`migrations/0001_init.sql`'s header
comment), preserved rather than silently changed, since switching would
be a real behavioral/schema change warranting its own milestone, not a
port detail. The standalone worker (`scripts/run-job-worker.ts`) has
still only been exercised against local SQLite and the in-memory
Postgres test fakes in this repo's test suite — genuine multi-process,
multi-machine Postgres concurrency has real automated test coverage now
(`lib/jobs/__tests__/jobQueueConcurrency.test.ts`, plus a
`TEST_DATABASE_URL`-gated real-server version) but has not been run
against an actual hosted multi-instance deployment.

## Object storage

- **Development**: local disk, `LocalStorageBackend` (`dashboard/lib/storage/StorageBackend.ts`) / `LocalArtifactStorage` (`research/artifact_storage.py`).
- **Production**: any S3-compatible provider (AWS S3, Cloudflare R2, Backblaze
  B2, MinIO, ...) via `ProductionObjectStorageBackend` (Node,
  `@aws-sdk/client-s3`) and `S3ArtifactStorage` (Python, `boto3`). Both are
  real, tested implementations (mocked S3 client in unit tests — no cloud
  resources required to run the test suite).
- **Milestone 33.2 — wired end to end.** Every production-critical reader and
  writer now routes through this abstraction instead of raw `node:fs` /
  Python `Path`/`open()` calls:
  - Node: `lib/discovery.ts` (the shared low-level primitive under
    `lib/loaders.ts` and every `lib/*Projections.ts`/`lib/gameEnvironment.ts`/
    etc. reader) now calls `lib/storage/getStorage.ts::getStorage()` — a
    lazy singleton mirroring `lib/db/executor.ts::getExecutor()`'s exact
    shape, resolved once via `resolveStorageBackend()`. Every function in
    `discovery.ts` is `async` now; its external contract (still absolute,
    `artifactPath()`-shaped paths in and out) is otherwise unchanged, so
    callers only needed `await` added, not a rewrite.
  - Python: `research/storage.py::save_json()` and every persistence module
    that previously wrote raw JSON/CSV/bytes directly to disk (`dfs/`,
    `ownership/`, `optimizer/`, `bluecollar/`, `evaluation/`,
    `native_projections/`, `external_projections/`, `projection_engine/`,
    `big_money_ml/`, `fantasypros/`, `player_identity/`,
    `research/game_environment/`, `dfs/providers/draftkings_csv_storage.py`)
    now calls `research/artifact_storage.py::resolve_artifact_storage()`
    (JSON, plus new `write_bytes`/`write_text`/`read_bytes`/`delete` methods
    for the two CSV-writing call sites and the raw-CSV-upload storage module).
  - Both languages resolve the SAME five `OBJECT_STORAGE_*` env vars to the
    SAME bucket, so a Process/Refresh run on one machine and a member read on
    another see identical artifacts once object storage is configured.

### Canonical object keys

Every object key is simply the artifact's existing repo-relative path,
forward-slash-normalized — the smallest possible migration, since every
artifact directory (`research_output/`, `predictions/`, `dfs_input/`,
`native_projection_snapshots/`, etc.) was already organized
`<artifact-dir>/<date>/[<slate-id>/]<filename>`, which is already
date-scoped, already slate-scoped where a slate can genuinely collide
(ownership, DK CSV uploads, ML forward-results), and already collision-free
across Main/Turbo/Night (distinct `slate-id` path segments). No new key
hierarchy was invented. Both languages derive this identically:
`dashboard/lib/artifactRoot.ts::toArtifactKey()` (Node) and
`research/artifact_storage.py::to_artifact_key()` (Python) each resolve a
path to an artifact-root-relative, forward-slash string; a path genuinely
outside the artifact root (a scratch/temp file) falls back to its resolved
absolute-path string instead of erroring, since such a path is a deliberate
"don't go through object storage" signal, not a bug.

### Model artifacts (`data/models/`)

**Decision: object storage, cached to local disk once per process, never
re-fetched per inference call.** `data/models/mlb/{hitter,pitcher}/v1/` is
small (~1.7 MB total: `model.joblib` + metadata/metrics JSON per player
type) and is `.gitignore`d by existing project convention (Milestone 32.2:
"reproducible by re-running training against the warehouse, never source") —
so baking it into a Docker image would mean either breaking that convention
(committing binary model artifacts to git) or a separate image-build step
outside this milestone's scope. Object storage keeps the existing
"generated, not source" convention intact and reuses the SAME bucket/
abstraction as every other artifact, rather than a third mechanism.
`historical_models/pitcher_v1/persistence.py::load_model()` (reused
verbatim by `hitter_v1` and by `big_money_ml/{artifact,hitter_artifact}.py`
— the one real choke point for every model-loading call site in this repo)
now checks local disk first and only calls
`resolve_artifact_storage().read_bytes()` on a cache miss, writing the
result to local disk before returning — so a warm process never makes a
network call to load a model it already has. A process picks up a newly
trained model version only via restart (this package has always assumed a
fixed version per process lifetime); no cache-invalidation logic exists or
is needed. **Training remains fully out of scope for this milestone** — no
model was retrained, and `save_model()` still only writes locally (a
freshly trained model must be uploaded to the bucket as a manual/deploy-time
step — see the seeding inventory below).

### Historical warehouse (`data/historical/mlb/`, `historical_mlb/`)

**Decision: stays out of normal production runtime entirely, by design.**
It's `.gitignore`d (`/data/historical/`) and was already never read by any
live-inference or member-facing code path — `historical_mlb/` builds and
`historical_models/*/train.py` consumes it strictly offline, against
whatever warehouse exists on the machine running the training command. This
milestone changes nothing here: no warehouse code was routed through the
object-storage abstraction, and none should be — a live member request
never needs it, and routing gigabytes of historical training data through
the same bucket used for member-facing snapshots would be pure unnecessary
complexity (and unnecessary object-storage cost) with no product benefit.

### Health check

`GET`-style readiness in both languages, SAFE-only (never a credential,
endpoint, bucket-contents, or object-key value):
- Node: `lib/systemReadiness.ts::getObjectStorageReadiness()` → `{ backend:
  "local" | "object", status: "CONNECTED" | "NOT_CONFIGURED" | "ERROR",
  detail }`. Feeds the Admin System page's Object Storage card
  (`/admin/system`), which now also shows which backend is actually active
  ("Local disk" vs "S3-compatible"), not just its status.
- Python: `research/artifact_storage.py::check_artifact_storage_health()` →
  `{ backend, connectivity: "healthy" | "unreachable" | "not_configured",
  bucket, detail }` — same shape and semantics, callable directly or via
  `python scripts/check_storage_health.py` (prints one JSON line). Uses
  `HeadBucket`, which only confirms reachability, never touches or lists any
  object.

### Production seeding inventory

What a first hosted deployment needs uploaded into the bucket before it can
serve real traffic, versus what must NOT be uploaded:

| Artifact | Seed before launch? | Why |
|---|---|---|
| `data/models/mlb/{hitter,pitcher}/v1/*` | **REQUIRED** | Live inference (Native/AI/Big Money ML projections) fails loudly (`FileNotFoundError`) without it — see Model artifacts above. |
| `research_output/`, `predictions/`, `dfs_input/`, `ownership_predictions/`, `native_projection_snapshots/`, `ai_projection_snapshots/`, `ml_projection_snapshots/`, `game_environment_snapshots/`, `bluecollar_projection_snapshots/`, `fantasypros_snapshots/`, `external_projection_snapshots/`, `adjusted_projection_snapshots/`, `lineups/`, `results/`, `ml_forward_results/`, `evaluations/`, `ownership_evaluations/`, `actual_ownership/` | Optional | Slate/prediction/evaluation history. A fresh empty bucket is a valid, honest starting state — the product just shows "no data yet" until the first real Process/Refresh run populates it. Pre-seeding old local dev/test artifacts would misrepresent real prediction history (CLAUDE.md's evaluation-integrity rules) and is explicitly NOT recommended. |
| `player_identity_crosswalk/`, `player_identity_snapshots/` | Optional | Rebuilds itself from live MLB rosters on the first identity refresh; pre-seeding saves that one refresh's cold-start cost, nothing more. |
| `data/historical/mlb/` (historical warehouse), `historical_mlb/` outputs | **DO NOT UPLOAD** | Offline-training-only (see above) — has no role in serving member traffic and would add nothing but cost/clutter to the production bucket. |
| Any local dev/test cache (`research/cache.py`'s cache dir, `data/draftkings_unofficial/` dev-only archive) | **DO NOT UPLOAD** | Regenerable, dev-only, or explicitly out of the artifact-storage abstraction by design (Category D/E — see this module's own docstrings). |

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

### Milestone 33.3 — the "no requirements.txt" gap noted above is closed

`requirements.txt` / `requirements-dev.txt` now exist at the repo root (see
"Runtime & build reproducibility" above for the full audit and pinning
rationale). `.python-version` and `.nvmrc` pin the exact interpreter/runtime
versions this was validated against. A `Dockerfile` and `.dockerignore` exist
at the repo root but have not been through a real `docker build` (Docker was
not available in the development environment) — treat as reviewed, not
verified, until one is run.

### Milestone 33.4 — `tsx` added as a pinned production dependency

`dashboard/package.json`: `tsx@4.23.12` (exact-pinned, `dependencies` not
`devDependencies` — needed at production runtime, not just in development).
Fixes a real, live-confirmed startup crash in `scripts/run-job-worker.ts`
(and a previously-unverified latent copy of the same bug in
`scripts/migrate-postgres-schema.ts`) — see "Node" under "Runtime & build
reproducibility" above for the full root-cause explanation. Docker was
still not available in this milestone's development environment either
(re-checked) — same "reviewed, not build-verified" status as the
Dockerfile above.
