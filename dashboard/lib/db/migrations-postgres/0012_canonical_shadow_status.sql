-- M3E: shadow ingestion status/observability -- additive columns on
-- the EXISTING `slates` table (M1's canonical foundation), rather than
-- a new parallel status table, per M3F's explicit "prefer existing
-- schema where appropriate" instruction: `slates` is already keyed by
-- the exact identity (sport, site, provider, provider_slate_id) this
-- status needs to report against.
--
-- Numbered 0012 here (this directory's next number) though its SQLite
-- counterpart is 0011 -- the two migration directories already diverge
-- in numbering (see 0009_ordering_sequence_columns.sql's own header
-- comment for the established precedent).
--
-- See migrations/0011_canonical_shadow_status.sql (SQLite dialect) for
-- the full rationale -- identical DDL, shared verbatim across both
-- dialects like every other migration in this project.
--
-- MIGRATION SAFETY NOTE (M3G): scanned clean -- eleven additive ALTER
-- TABLE ADD COLUMN statements only, no DROP/TRUNCATE/destructive ALTER.

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
