-- Milestone 32.4: Big Money ML Owner Optimizer + Results Tracking.
--
-- A NEW, finer-grained feature flag than the page-level ones seeded in
-- 0002 -- 'mlb.optimizer' already gates the whole Optimizer page
-- (PRODUCTION, everyone with that entitlement can open it). This flag
-- gates ONE SPECIFIC CAPABILITY inside that already-open page: whether
-- "Big Money ML" is a selectable Projection Source. Seeded ADMIN_ONLY
-- so shipping this migration causes ZERO behavior change for any
-- current member -- they still see native/ai/fantasypros/independent/
-- external/adjusted exactly as before; only ADMIN can additionally
-- select Big Money ML, via lib/entitlements/featureVisibility.ts's
-- existing isFeatureVisibleToUser() gate (ADMIN_ONLY -> visible only to
-- ADMIN, regardless of entitlement -- no new gating mechanism invented).
--
-- INSERT OR IGNORE so re-running this migration file is always a safe
-- no-op, same discipline as 0002.

INSERT OR IGNORE INTO entitlements (key, sport_code, label) VALUES
  ('mlb.big_money_ml_optimizer', 'MLB', 'Big Money ML Optimizer');

INSERT OR IGNORE INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.big_money_ml_optimizer', 'MLB', 'Big Money ML Optimizer', 'ADMIN_ONLY', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
