-- M3E: shadow ingestion status/observability -- additive columns on
-- the EXISTING `slates` table (M1's canonical foundation), rather than
-- a new parallel status table, per M3F's explicit "prefer existing
-- schema where appropriate" instruction: `slates` is already keyed by
-- the exact identity (sport, site, provider, provider_slate_id) this
-- status needs to report against.
--
-- Gap this closes: before this migration, `slates` only ever reflected
-- the MOST RECENTLY SUCCESSFUL promotion -- a validation-rejected
-- attempt, an unknown-schemaVersion attempt, or a hash-mismatch-on-
-- rehydration attempt left ZERO trace anywhere in Postgres. These
-- columns let dashboard/lib/db/canonicalPromotion.ts (M3B) record every
-- attempt, success or failure, so M3J's admin monitor can actually
-- diagnose automatic ingestion health.
--
-- Purely additive: eleven nullable/defaulted ALTER TABLE ADD COLUMN
-- statements, no data migration, no destructive change. slate_status
-- (the existing, unrelated Milestone 29 table) is untouched.

ALTER TABLE slates ADD COLUMN last_attempt_at TEXT;
ALTER TABLE slates ADD COLUMN last_success_at TEXT;
ALTER TABLE slates ADD COLUMN last_failure_at TEXT;
ALTER TABLE slates ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE slates ADD COLUMN last_error_type TEXT;
ALTER TABLE slates ADD COLUMN last_error_summary TEXT;
ALTER TABLE slates ADD COLUMN player_count INTEGER;
ALTER TABLE slates ADD COLUMN resolved_identity_count INTEGER;
ALTER TABLE slates ADD COLUMN unresolved_identity_count INTEGER;
ALTER TABLE slates ADD COLUMN review_required_count INTEGER;
ALTER TABLE slates ADD COLUMN is_semantic_duplicate INTEGER CHECK (is_semantic_duplicate IN (0,1));
