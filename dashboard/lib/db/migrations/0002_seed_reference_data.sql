-- Reference/catalog data: 4 sports (only MLB is LIVE), the 2 launch
-- plans, and one feature_flags + entitlements row per existing MLB
-- dashboard nav item -- all seeded PRODUCTION, so shipping auth causes
-- ZERO behavior change for any current feature; it's simply now gated
-- by a real session + entitlement check instead of being wide open.
--
-- INSERT OR IGNORE (keyed on each table's natural primary key) so
-- re-running this migration file is always a safe no-op.

INSERT OR IGNORE INTO sports (code, name, status, sort_order) VALUES
  ('MLB', 'MLB', 'LIVE', 0),
  ('NFL', 'NFL', 'COMING_SOON', 1),
  ('NBA', 'NBA', 'COMING_SOON', 2),
  ('NHL', 'NHL', 'COMING_SOON', 3);

INSERT OR IGNORE INTO plans (id, name, price_cents, billing_interval, trial_days, is_active, created_at) VALUES
  ('weekly',  'Weekly',  1099, 'WEEKLY',  3, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('monthly', 'Monthly', 2999, 'MONTHLY', 3, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT OR IGNORE INTO entitlements (key, sport_code, label) VALUES
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
  ('mlb.results',        'MLB', 'Results');

INSERT OR IGNORE INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.command_center', 'MLB', 'Command Center', 'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.research',       'MLB', 'Research',       'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.environment',    'MLB', 'Environment',    'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.pitchers',       'MLB', 'Pitchers',       'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.hitters',        'MLB', 'Hitters',        'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.stacks',         'MLB', 'Stacks',         'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.weather',        'MLB', 'Weather',        'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.vegas',          'MLB', 'Vegas',          'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.ownership',      'MLB', 'Ownership',      'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.optimizer',      'MLB', 'Optimizer',      'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.ai_projections', 'MLB', 'AI Projections', 'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.external_projections', 'MLB', 'External Projections', 'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.portfolio',      'MLB', 'Portfolio',      'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  ('mlb.results',        'MLB', 'Results',        'PRODUCTION', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
