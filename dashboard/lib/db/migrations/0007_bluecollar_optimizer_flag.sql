-- BlueCollar Live Projection Integration.
--
-- A NEW, finer-grained feature flag (same pattern as 0006's
-- mlb.big_money_ml_optimizer) gating ONE SPECIFIC CAPABILITY inside the
-- already-open Optimizer page: whether "BlueCollar" is a selectable
-- Projection Source. Seeded ADMIN_ONLY so shipping this migration
-- causes ZERO behavior change for any current member -- they still see
-- native/ai/ml/fantasypros/independent/external/adjusted exactly as
-- before; only ADMIN can additionally select BlueCollar, via
-- lib/entitlements/featureVisibility.ts's existing
-- isFeatureVisibleToUser() gate (ADMIN_ONLY -> visible only to ADMIN,
-- regardless of entitlement -- no new gating mechanism invented).
--
-- INSERT OR IGNORE so re-running this migration file is always a safe
-- no-op, same discipline as 0002/0006.

INSERT OR IGNORE INTO entitlements (key, sport_code, label) VALUES
  ('mlb.bluecollar_optimizer', 'MLB', 'BlueCollar Optimizer');

INSERT OR IGNORE INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.bluecollar_optimizer', 'MLB', 'BlueCollar Optimizer', 'ADMIN_ONLY', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
