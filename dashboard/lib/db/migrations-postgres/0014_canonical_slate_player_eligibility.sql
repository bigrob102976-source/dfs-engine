-- M6D: additive columns on the EXISTING slate_players table for REAL
-- MLB lineup-eligibility state -- audited first (see M6's own Step 0):
-- no existing table/column in this schema stores eligibility_status/
-- optimizer_eligible/batting_order anywhere; position_eligibility_json/
-- roster_slot_eligibility_json describe DK ROSTER-SLOT eligibility (which
-- lineup slots a player can fill), a completely different concept from
-- MLB LINEUP-CONFIRMATION eligibility (dfs/eligibility.py's STARTING_
-- PITCHER/STARTING_HITTER/etc.) -- so a genuinely new, additive set of
-- columns is required, kept on the SAME row (never a new sibling table)
-- per M6D's own preference for "canonical CURRENT eligibility with the
-- canonical slate-player serving state rather than recomputing the
-- entire research join on every customer request."
--
-- game_id is NOT added here -- slate_players.game_id already exists
-- (migrations-postgres/0010_slate_identity_foundation.sql), currently
-- always NULL because nothing has populated it yet; M6B's job is to
-- START populating that EXISTING column, not add a new one.
--
-- eligibility_status/optimizer_eligible start NULL/0 for every existing
-- row (never computed yet) -- CanonicalPostgresServingBackend treats a
-- NULL eligibility_status as "not yet computed" (a distinct, honest
-- state), never as an assumed-eligible default (M6 rule #9).
--
-- eligibility_computed_at is separate from the row's own updated_at
-- (M6E: acquisition truth -- salary/identity -- and research/enrichment
-- truth -- eligibility -- are kept conceptually and timestamp-wise
-- distinct, so an eligibility recompute is never confused with, or
-- mistaken for, a new salary/identity promotion).
--
-- Numbered 0014 here; SQLite counterpart is 0013 -- the two migration
-- directories have diverged in numbering since 0009 (see that file's
-- own header comment for the established precedent).
--
-- MIGRATION SAFETY NOTE: scanned clean -- four additive ALTER TABLE ADD
-- COLUMN statements only, no DROP/TRUNCATE/destructive ALTER, no DELETE.

ALTER TABLE slate_players ADD COLUMN eligibility_status TEXT;
ALTER TABLE slate_players ADD COLUMN optimizer_eligible INTEGER CHECK (optimizer_eligible IN (0,1));
ALTER TABLE slate_players ADD COLUMN batting_order INTEGER;
ALTER TABLE slate_players ADD COLUMN eligibility_computed_at TEXT;
