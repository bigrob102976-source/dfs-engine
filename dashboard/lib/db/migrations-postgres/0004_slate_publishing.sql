-- Milestone 29: Admin Slate Publishing + Member-Ready Data.
--
-- Two tables, deliberately separate concerns:
--
--   slate_status         Mutable, ONE row per (slate_date, slate_id) --
--                         "what is the current state of this slate right
--                         now" (DRAFT/PROCESSING/READY/PUBLISHED/PARTIAL/
--                         ERROR/ARCHIVED), plus the artifact paths the
--                         most recent process/refresh run produced, and
--                         (only while published) a copy of the CURRENT
--                         published version's pinned snapshot paths so a
--                         member-facing read is a single-row lookup.
--
--   slate_publish_history Append-only, ONE row per PUBLISH EVENT -- never
--                         updated or deleted (see lib/db/auditLog.ts's
--                         identical convention). This is the permanent
--                         version record the milestone requires ("Do not
--                         overwrite historical publish records"); unpublish
--                         only clears slate_status's pointer fields, it
--                         never touches history.
--
-- Snapshot paths are stored as repo-root-relative strings (matching every
-- existing artifact path already recorded elsewhere in this project,
-- e.g. dfs_input/2026-08-18/dk_player_pool_....json) so a member-facing
-- loader can read the exact same file an admin's process/refresh run
-- produced, pinned, instead of re-globbing for "latest" and potentially
-- picking up a newer, unpublished, in-progress refresh.

CREATE TABLE slate_status (
  id                      TEXT PRIMARY KEY,
  slate_date              TEXT NOT NULL,
  slate_id                TEXT NOT NULL,
  slate_label             TEXT,
  status                  TEXT NOT NULL CHECK (status IN ('DRAFT','PROCESSING','READY','PUBLISHED','PARTIAL','ERROR','ARCHIVED')) DEFAULT 'DRAFT',

  -- Most recent process/refresh run's own artifacts (may be AHEAD of what
  -- is currently published -- these are what /admin/slates shows, never
  -- what a member-facing loader reads).
  pool_path               TEXT,
  match_report_path       TEXT,
  ownership_path          TEXT,
  native_snapshot_path    TEXT,
  ai_snapshot_path        TEXT,
  vegas_snapshot_path     TEXT,
  research_snapshot_path  TEXT,
  source_hash             TEXT,
  source_provenance       TEXT,
  validation_json         TEXT,
  last_processed_at       TEXT,
  last_refreshed_at       TEXT,

  -- The CURRENTLY LIVE published version's pinned paths -- NULL whenever
  -- status != 'PUBLISHED'. Kept in sync with the latest matching row in
  -- slate_publish_history at publish/unpublish time.
  published_version       INTEGER,
  published_at            TEXT,
  published_by            TEXT REFERENCES users(id),
  published_pool_path             TEXT,
  published_match_report_path     TEXT,
  published_ownership_path        TEXT,
  published_native_snapshot_path  TEXT,
  published_ai_snapshot_path      TEXT,
  published_vegas_snapshot_path   TEXT,
  published_research_snapshot_path TEXT,
  published_source_hash           TEXT,

  created_at              TEXT NOT NULL,
  updated_at              TEXT NOT NULL,
  UNIQUE(slate_date, slate_id)
);
CREATE INDEX idx_slate_status_date ON slate_status(slate_date);
CREATE INDEX idx_slate_status_status ON slate_status(status);

CREATE TABLE slate_publish_history (
  id                      TEXT PRIMARY KEY,
  slate_date              TEXT NOT NULL,
  slate_id                TEXT NOT NULL,
  slate_label             TEXT,
  data_version            INTEGER NOT NULL,
  event                   TEXT NOT NULL CHECK (event IN ('PUBLISHED','UNPUBLISHED','ARCHIVED')),
  published_at            TEXT NOT NULL,
  published_by            TEXT REFERENCES users(id),
  source_hash             TEXT,
  pool_path               TEXT,
  match_report_path       TEXT,
  ownership_path          TEXT,
  native_snapshot_path    TEXT,
  ai_snapshot_path        TEXT,
  vegas_snapshot_path     TEXT,
  research_snapshot_path  TEXT
);
CREATE INDEX idx_slate_publish_history_date_slate ON slate_publish_history(slate_date, slate_id);
CREATE INDEX idx_slate_publish_history_version ON slate_publish_history(slate_date, slate_id, data_version);
