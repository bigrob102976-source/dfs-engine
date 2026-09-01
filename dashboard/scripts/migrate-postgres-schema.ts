// Milestone 33.1: THE production migration command -- applies every
// not-yet-applied dashboard/lib/db/migrations-postgres/*.sql file to the
// database DATABASE_URL points at. Schema only -- never touches or
// copies data (see scripts/migrate-sqlite-to-postgres.ts for the
// separate, one-time SQLite-data-import tool, which already calls this
// same runPostgresMigrations() as its first step before copying rows).
//
// This script itself never runs implicitly on app startup or on the
// first request (see lib/db/executor.ts's own docstring). CORRECTION
// (M2, 2026-09-01): that does NOT mean production migrations only ever
// happen via a human manually running this file -- Railway's own
// deploy configuration (outside this repo, in its project/service
// settings) invokes exactly this command automatically after every
// deploy. Confirmed live: migrations 0010 and 0011 both auto-applied
// to production within seconds of their respective deploys completing.
// Every migration merged to main should be written and reviewed as if
// it WILL run against production immediately on merge -- see
// lib/db/migrationSafety.ts (M3G) for the resulting guardrail.
//
// Usage (from dashboard/, Node 22.5+):
//
//   DATABASE_URL=postgres://user:pass@host:5432/db node scripts/migrate-postgres-schema.ts
//
// Safe to run repeatedly -- already-applied migrations are skipped
// (recorded in the schema_migrations table), so this is the same
// command for "first deploy of a brand-new database" and "apply the
// one new migration a later release added."

import { getPostgresPool, listPostgresMigrationFiles, runPostgresMigrations } from "../lib/db/postgresClient.ts";

async function main() {
  if (!process.env.DATABASE_URL) {
    console.error("DATABASE_URL is not set -- refusing to run. This command only ever targets the database DATABASE_URL points at.");
    process.exitCode = 1;
    return;
  }

  const expected = listPostgresMigrationFiles();
  console.log(`${expected.length} migration file(s) found on disk.`);

  const pool = getPostgresPool();
  try {
    const result = await runPostgresMigrations(pool);
    if (result.applied.length === 0) {
      console.log("Schema already up to date -- nothing to apply.");
    } else {
      console.log(`Applied ${result.applied.length} migration(s):`);
      for (const filename of result.applied) console.log(`  + ${filename}`);
    }
    if (result.alreadyApplied.length > 0) {
      console.log(`${result.alreadyApplied.length} migration(s) were already applied (skipped).`);
    }
  } finally {
    await pool.end();
  }
}

main().catch((err) => {
  console.error("Migration failed:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
