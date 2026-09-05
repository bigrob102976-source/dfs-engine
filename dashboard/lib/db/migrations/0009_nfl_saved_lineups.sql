-- NFL M14: saved lineups for the late-swap / game-day workflow. One row
-- per user-saved lineup. Unlike the research/ML snapshot artifacts
-- elsewhere in this project (immutable, never overwritten), a saved
-- lineup is genuinely mutable, user-owned state -- late swap reads the
-- row, updates only the unlocked slots, and writes the SAME row back
-- (updated_at bumped, id unchanged) rather than creating a new
-- immutable file every time, exactly like slate_status's mutable
-- "current state" pointer (lib/db/slateStatus.ts) rather than
-- slate_publish_history's append-only log.
--
-- The full slot assignment is kept as one JSON blob (slots_json),
-- mirroring slate_status's validation_json/change_report_json
-- discipline for "small JSON blob in a column" -- a saved lineup is
-- always read/written as one whole unit (build -> save -> late-swap ->
-- re-save), never queried slot-by-slot, so a normalized child table
-- would add complexity with no real query benefit.
--
-- Lock state is NEVER stored here -- nfl/game_lock.py computes it fresh
-- from each slot's real game_start_utc against the current real time on
-- every read, so a lineup opened days apart always reflects the truth
-- at that moment rather than a stale cached boolean.

CREATE TABLE nfl_saved_lineups (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  draft_group_id INTEGER NOT NULL,
  slate_date TEXT NOT NULL,
  mode TEXT NOT NULL,
  stack_config_json TEXT NOT NULL,
  slots_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_nfl_saved_lineups_user_draft_group ON nfl_saved_lineups (user_id, draft_group_id);
