-- M2H: additive promotion metadata for the canonical `slates` table
-- (created by 0009_slate_identity_foundation.sql). Needed so a
-- promoted row records EXACTLY which R2 artifacts it represents and
-- when it was promoted -- required for the M2 shadow-CURRENT write
-- (dashboard/lib/db/canonicalPromotion.ts) and its M2J rehydration
-- counterpart to be auditable.
--
-- Reused rather than duplicated: raw_hash, normalized_hash,
-- schema_version, and fetched_at already exist on `slates` from M1 --
-- this migration adds ONLY the three genuinely new fields M2H's own
-- audit found missing (the artifact PATHS, and the promotion TIMESTAMP,
-- which is distinct from fetched_at -- a slate can be fetched and
-- normalized without yet being promoted, e.g. a REJECTED validation
-- state).
--
-- Purely additive: three nullable ALTER TABLE ADD COLUMN statements, no
-- data migration, no destructive change. slate_status (the EXISTING,
-- unrelated Milestone 29 table) is untouched -- M2H's own instruction
-- was explicit not to alter its semantics.

ALTER TABLE slates ADD COLUMN current_normalized_artifact_path TEXT;
ALTER TABLE slates ADD COLUMN current_raw_artifact_path TEXT;
ALTER TABLE slates ADD COLUMN promoted_at TEXT;
