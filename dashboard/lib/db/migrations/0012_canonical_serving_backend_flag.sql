-- M5C: the admin-controlled serving-backend feature flag. Reuses the
-- EXISTING feature_flags/entitlements mechanism and admin UI/API
-- surface (/api/admin/features/[key]/state, lib/entitlements/
-- featureVisibility.ts::isFeatureVisibleToUser) -- no new gating
-- mechanism invented, same pattern as 0006/0007's optimizer-source
-- flags.
--
-- Seeded ADMIN_ONLY: for THIS flag, ADMIN_ONLY means "an ADMIN may
-- explicitly opt a request into CANONICAL_POSTGRES serving; every
-- MEMBER always gets LEGACY_R2, with no way to override" (see
-- dashboard/lib/servingBackend/config.ts) -- ships with ZERO behavior
-- change for any current member. DISABLED would refuse canonical
-- serving even for ADMIN (a full kill switch); PRODUCTION would make
-- canonical the default for everyone -- that state is NOT reached by
-- this migration and must never be set without the M5M cutover gate's
-- full parity/canary/rollback proof already passing.
--
-- INSERT OR IGNORE so re-running this migration file is always a safe
-- no-op, same discipline as 0002/0006/0007.

INSERT OR IGNORE INTO entitlements (key, sport_code, label) VALUES
  ('mlb.canonical_postgres_serving', 'MLB', 'Canonical Postgres Serving (M5 canary)');

INSERT OR IGNORE INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.canonical_postgres_serving', 'MLB', 'Canonical Postgres Serving (M5 canary)', 'ADMIN_ONLY', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
