-- BREAK-GLASS ADMIN CSV UPLOAD: widens jobs.job_type to add
-- REFRESH_CANONICAL_DATE -- the durable job Phase 7 of the admin-CSV
-- import enqueues after a successful canonical promotion, running
-- scripts/refresh-research-and-eligibility.ts::runRefresh() (research/
-- identity/eligibility/Native projections/ownership, date-level, reused
-- unmodified from the existing automatic-refresh path) via the SAME
-- durable job queue (lib/jobs/queue.ts) Process/Refresh Slate already
-- uses -- never a bare fire-and-forget promise.
--
-- SQLite cannot ALTER a CHECK constraint in place (see
-- migrations/0003_stripe_billing.sql's own precedent for this exact
-- pattern) -- the table is rebuilt (create-new/copy/drop/rename). All
-- existing columns/data/indexes are preserved exactly; only the
-- job_type CHECK list changes.

CREATE TABLE jobs_new (
  id                 TEXT PRIMARY KEY,
  job_type           TEXT NOT NULL CHECK (job_type IN ('PROCESS_SLATE','REFRESH_SLATE','BUILD_LINEUPS','RESULTS_COLLECTION','MODEL_EVALUATION','REFRESH_CANONICAL_DATE')),
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

INSERT INTO jobs_new (
  id, job_type, slate_date, slate_id, status, created_by, created_at, started_at, finished_at, updated_at,
  progress, current_step, error_code, safe_error_message, worker_id, attempt_count, max_attempts, payload_json
)
SELECT
  id, job_type, slate_date, slate_id, status, created_by, created_at, started_at, finished_at, updated_at,
  progress, current_step, error_code, safe_error_message, worker_id, attempt_count, max_attempts, payload_json
FROM jobs;

DROP TABLE jobs;
ALTER TABLE jobs_new RENAME TO jobs;

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_slate ON jobs(slate_date, slate_id);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE UNIQUE INDEX idx_jobs_active_uniqueness ON jobs(slate_date, slate_id, job_type) WHERE status IN ('QUEUED','RUNNING');
