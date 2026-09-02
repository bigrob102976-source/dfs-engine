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
-- Numbered 0013 here; SQLite counterpart is 0012 -- the two migration
-- directories have diverged in numbering since 0009 (see that file's
-- own header comment for the established precedent).
--
-- MIGRATION SAFETY NOTE: scanned clean -- two additive INSERTs only, no
-- DROP/TRUNCATE/destructive ALTER.

INSERT INTO entitlements (key, sport_code, label) VALUES
  ('mlb.canonical_postgres_serving', 'MLB', 'Canonical Postgres Serving (M5 canary)')
ON CONFLICT (key) DO NOTHING;

INSERT INTO feature_flags (key, sport_code, label, state, updated_at) VALUES
  ('mlb.canonical_postgres_serving', 'MLB', 'Canonical Postgres Serving (M5 canary)', 'ADMIN_ONLY', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ON CONFLICT (key) DO NOTHING;
