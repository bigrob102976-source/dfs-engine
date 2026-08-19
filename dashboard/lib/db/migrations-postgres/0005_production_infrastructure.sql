-- Milestone 30: Production Infrastructure Foundation.
--
-- jobs: persistent record of every background pipeline run (replaces
-- Milestone 29's in-process, fire-and-forget runSlatePipeline() call --
-- see lib/jobs/queue.ts). A QUEUED/RUNNING row for the same
-- (slate_date, slate_id, job_type) is enforced unique at the DB level
-- (idx_jobs_active_uniqueness) so a duplicate Process/Refresh click can
-- never silently start a second expensive pipeline run concurrently --
-- see this milestone's "JOB IDEMPOTENCY" requirement.
--
-- worker_heartbeats: one row per worker process, updated periodically
-- while alive -- lib/jobs/heartbeat.ts derives ONLINE/STALE/OFFLINE from
-- how recently a row was touched, never from in-process memory (a
-- worker process restarting or the web process restarting must not by
-- itself make a live worker look offline, or vice versa).
--
-- users.beta_access_*: Private Beta gate (PRIVATE_BETA=true env flag --
-- see lib/env.ts). Deliberately NOT modeled as a user_entitlements row:
-- beta access is an ACCOUNT-level gate in front of the product entirely
-- (like disabled_at), not a per-feature entitlement, so it doesn't
-- belong in the sport/feature-scoped entitlements catalog. A non-null
-- beta_access_granted_at means "this user may use the member product
-- while PRIVATE_BETA is enabled" -- ADMIN always can, regardless.

CREATE TABLE jobs (
  id                 TEXT PRIMARY KEY,
  job_type           TEXT NOT NULL CHECK (job_type IN ('PROCESS_SLATE','REFRESH_SLATE','BUILD_LINEUPS','RESULTS_COLLECTION','MODEL_EVALUATION')),
  slate_date         TEXT,
  slate_id           TEXT,
  status             TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELED')) DEFAULT 'QUEUED',
  created_by         TEXT REFERENCES users(id),
  created_at         TEXT NOT NULL,
  started_at         TEXT,
  finished_at        TEXT,
  updated_at         TEXT NOT NULL,
  progress           INTEGER NOT NULL DEFAULT 0,
  current_step       TEXT,
  error_code         TEXT,
  safe_error_message TEXT,
  worker_id          TEXT,
  attempt_count      INTEGER NOT NULL DEFAULT 0,
  max_attempts       INTEGER NOT NULL DEFAULT 3,
  payload_json       TEXT
);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_slate ON jobs(slate_date, slate_id);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
-- Idempotency guard: at most one QUEUED-or-RUNNING job per (slate,
-- job_type) at a time. SUCCEEDED/FAILED/CANCELED rows are exempt (kept
-- forever as history), so re-processing the same slate later is normal.
CREATE UNIQUE INDEX idx_jobs_active_uniqueness ON jobs(slate_date, slate_id, job_type) WHERE status IN ('QUEUED','RUNNING');

CREATE TABLE worker_heartbeats (
  worker_id     TEXT PRIMARY KEY,
  last_seen_at  TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'ONLINE',
  metadata_json TEXT
);

ALTER TABLE users ADD COLUMN beta_access_granted_at TEXT;
ALTER TABLE users ADD COLUMN beta_access_granted_by TEXT REFERENCES users(id);
