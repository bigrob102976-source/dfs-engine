-- M32.7: Early Slate Projection Readiness + Automatic Lineup Promotion.
--
-- Stores the Admin Change Report (lib/slateChangeReport.ts) produced by
-- the MOST RECENT Process/Refresh run for a slate -- a small JSON blob,
-- same discipline as validation_json (0004) -- so "what changed" can be
-- shown on the Slate Operations board without re-deriving it or adding
-- a new artifact-file write path. NULL for a slate that has never
-- completed a run since this column was added, or whose last run
-- errored before producing a report -- never fabricated.

ALTER TABLE slate_status ADD COLUMN change_report_json TEXT;
