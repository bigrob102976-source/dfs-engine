-- Milestone 32.4: Big Money ML Owner Optimizer + Results Tracking.
-- See lib/db/migrations/0006_big_money_ml_optimizer_flag.sql for the
-- full rationale -- identical seed, Postgres syntax.

INSERT INTO entitlements (key, sport_code, label) VALUES
  ('mlb.big_money_ml_optimizer', 'MLB', 'Big Money ML Optimizer')
ON CONFLICT (key) DO NOTHING;

INSERT INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.big_money_ml_optimizer', 'MLB', 'Big Money ML Optimizer', 'ADMIN_ONLY', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ON CONFLICT (key) DO NOTHING;
