-- Milestone 30: PostgreSQL dialect port of
-- lib/db/migrations/0002_seed_reference_data.sql -- identical seed rows,
-- `INSERT OR IGNORE` -> `INSERT ... ON CONFLICT DO NOTHING`,
-- `strftime('%Y-%m-%dT%H:%M:%fZ','now')` -> an equivalent millisecond-
-- precision UTC ISO-8601 expression (this project's own timestamp
-- convention, matching every value application code already writes).

INSERT INTO sports (code, name, status, sort_order) VALUES
  ('MLB', 'MLB', 'LIVE', 0),
  ('NFL', 'NFL', 'COMING_SOON', 1),
  ('NBA', 'NBA', 'COMING_SOON', 2),
  ('NHL', 'NHL', 'COMING_SOON', 3)
ON CONFLICT (code) DO NOTHING;

INSERT INTO plans (id, name, price_cents, billing_interval, trial_days, is_active, created_at) VALUES
  ('weekly',  'Weekly',  1099, 'WEEKLY',  3, 1, to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('monthly', 'Monthly', 2999, 'MONTHLY', 3, 1, to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ON CONFLICT (id) DO NOTHING;

INSERT INTO entitlements (key, sport_code, label) VALUES
  ('mlb.command_center', 'MLB', 'Command Center'),
  ('mlb.research',       'MLB', 'Research'),
  ('mlb.environment',    'MLB', 'Environment'),
  ('mlb.pitchers',       'MLB', 'Pitchers'),
  ('mlb.hitters',        'MLB', 'Hitters'),
  ('mlb.stacks',         'MLB', 'Stacks'),
  ('mlb.weather',        'MLB', 'Weather'),
  ('mlb.vegas',          'MLB', 'Vegas'),
  ('mlb.ownership',      'MLB', 'Ownership'),
  ('mlb.optimizer',      'MLB', 'Optimizer'),
  ('mlb.ai_projections', 'MLB', 'AI Projections'),
  ('mlb.external_projections', 'MLB', 'External Projections'),
  ('mlb.portfolio',      'MLB', 'Portfolio'),
  ('mlb.results',        'MLB', 'Results')
ON CONFLICT (key) DO NOTHING;

INSERT INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.command_center', 'MLB', 'Command Center', 'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.research',       'MLB', 'Research',       'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.environment',    'MLB', 'Environment',    'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.pitchers',       'MLB', 'Pitchers',       'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.hitters',        'MLB', 'Hitters',        'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.stacks',         'MLB', 'Stacks',         'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.weather',        'MLB', 'Weather',        'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.vegas',          'MLB', 'Vegas',          'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.ownership',      'MLB', 'Ownership',      'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.optimizer',      'MLB', 'Optimizer',      'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.ai_projections', 'MLB', 'AI Projections', 'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.external_projections', 'MLB', 'External Projections', 'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.portfolio',      'MLB', 'Portfolio',      'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
  ('mlb.results',        'MLB', 'Results',        'PRODUCTION', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ON CONFLICT (key) DO NOTHING;
