-- PostgreSQL dialect port of migrations/0017_admin_csv_import_job_type.sql
-- -- Postgres can alter a CHECK constraint in place (see
-- migrations-postgres/0003_stripe_billing.sql's own precedent), no
-- table rebuild needed.
--
-- MIGRATION-SAFETY: approved-destructive -- DROP CONSTRAINT below is
-- immediately paired with an ADD CONSTRAINT that only WIDENS the same
-- job_type CHECK list (adds 'REFRESH_CANONICAL_DATE'; every existing
-- allowed value is preserved) -- the one documented legitimate
-- exception in lib/db/migrationSafety.ts's own module docstring,
-- exactly like migrations-postgres/0003_stripe_billing.sql's own
-- subscriptions_provider_check widening.

ALTER TABLE jobs DROP CONSTRAINT jobs_job_type_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check CHECK (job_type IN ('PROCESS_SLATE','REFRESH_SLATE','BUILD_LINEUPS','RESULTS_COLLECTION','MODEL_EVALUATION','REFRESH_CANONICAL_DATE'));
