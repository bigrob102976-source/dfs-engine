-- M6D: additive columns on the EXISTING slate_players table for REAL
-- MLB lineup-eligibility state -- see migrations-postgres/
-- 0014_canonical_slate_player_eligibility.sql (this file's Postgres
-- counterpart) for the full rationale -- identical DDL, shared verbatim
-- across both dialects like every other migration in this project.
--
-- MIGRATION SAFETY NOTE: scanned clean -- four additive ALTER TABLE ADD
-- COLUMN statements only, no DROP/TRUNCATE/destructive ALTER, no DELETE.

ALTER TABLE slate_players ADD COLUMN eligibility_status TEXT;
ALTER TABLE slate_players ADD COLUMN optimizer_eligible INTEGER CHECK (optimizer_eligible IN (0,1));
ALTER TABLE slate_players ADD COLUMN batting_order INTEGER;
ALTER TABLE slate_players ADD COLUMN eligibility_computed_at TEXT;
