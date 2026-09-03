-- PROBABLE FIX: additive columns on the EXISTING slate_players table for
-- real, evidence-based probable-starter state (dfs/probable_starters.py)
-- -- see migrations/0016_probable_starters.sql (this file's SQLite
-- counterpart) for the full rationale -- identical DDL, shared verbatim
-- across both dialects like every other migration in this project.
--
-- lineup_confirmation: "CONFIRMED" (MLB's own official lineup has
-- posted) | "PROBABLE" (real-evidence inference, before that posts) |
-- NULL (not applicable -- BENCH/RELIEF_PITCHER/OUT/SCRATCHED/
-- LINEUP_UNCONFIRMED/UNMATCHED/AMBIGUOUS). probable_confidence/
-- probable_reason/projected_batting_order are only ever set alongside
-- eligibility_status = 'PROBABLE_HITTER'.
--
-- MIGRATION SAFETY NOTE: scanned clean -- four additive ALTER TABLE ADD
-- COLUMN statements only, no DROP/TRUNCATE/destructive ALTER, no DELETE.

ALTER TABLE slate_players ADD COLUMN lineup_confirmation TEXT;
ALTER TABLE slate_players ADD COLUMN probable_confidence TEXT;
ALTER TABLE slate_players ADD COLUMN probable_reason TEXT;
ALTER TABLE slate_players ADD COLUMN projected_batting_order INTEGER;
