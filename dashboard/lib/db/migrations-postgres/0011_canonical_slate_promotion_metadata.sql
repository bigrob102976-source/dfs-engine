-- M2H: additive promotion metadata for the canonical `slates` table
-- (created by 0010_slate_identity_foundation.sql on this dialect).
-- Numbered 0011 here (this directory's next number) though its SQLite
-- counterpart is 0010 -- the two migration directories already diverge
-- in numbering (see 0009_ordering_sequence_columns.sql's own header
-- comment for the established precedent).
--
-- See migrations/0010_canonical_slate_promotion_metadata.sql (SQLite
-- dialect) for the full rationale -- identical DDL, shared verbatim
-- across both dialects like every other migration in this project.

ALTER TABLE slates ADD COLUMN current_normalized_artifact_path TEXT;
ALTER TABLE slates ADD COLUMN current_raw_artifact_path TEXT;
ALTER TABLE slates ADD COLUMN promoted_at TEXT;
