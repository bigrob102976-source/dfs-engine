-- BlueCollar Live Projection Integration.
-- See lib/db/migrations/0007_bluecollar_optimizer_flag.sql for the full
-- rationale -- identical seed, Postgres syntax.

INSERT INTO entitlements (key, sport_code, label) VALUES
  ('mlb.bluecollar_optimizer', 'MLB', 'BlueCollar Optimizer')
ON CONFLICT (key) DO NOTHING;

INSERT INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.bluecollar_optimizer', 'MLB', 'BlueCollar Optimizer', 'ADMIN_ONLY', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ON CONFLICT (key) DO NOTHING;
