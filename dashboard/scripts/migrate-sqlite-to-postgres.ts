// Milestone 30: LOCAL admin/developer CLI for the one-time SQLite ->
// PostgreSQL data migration. Run from dashboard/ with Node 22.5+:
//
//   node scripts/migrate-sqlite-to-postgres.ts                 # dry run (default, safe)
//   node scripts/migrate-sqlite-to-postgres.ts --execute        # real migration
//   BIGMONEY_DB_PATH=./data/bigmoney.db DATABASE_URL=postgres://... node scripts/migrate-sqlite-to-postgres.ts --execute
//
// A dry run only reads the local SQLite file -- it never opens a
// PostgreSQL connection and DATABASE_URL is not required for it. A real
// run (--execute) requires DATABASE_URL, applies any not-yet-applied
// PostgreSQL migrations first (so the target schema exists), then copies
// every table via lib/db/dataMigration.ts's fail-closed orchestration.
//
// This script deliberately opens SQLite directly rather than going
// through lib/db/client.ts::getDb() -- that accessor intentionally
// throws whenever DATABASE_URL is configured (see its own docstring),
// which is exactly the situation this migration tool runs in (SQLite as
// the read-only SOURCE, Postgres as the WRITE target).

import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import {
  buildDryRunReport,
  MIGRATION_TABLES,
  runDataMigration,
  type MigrationRow,
  type MigrationSource,
  type MigrationTarget,
} from "../lib/db/dataMigration.ts";
import { getPostgresPool, runPostgresMigrations, type PostgresQueryable } from "../lib/db/postgresClient.ts";

function resolveSqlitePath(): string {
  return process.env.BIGMONEY_DB_PATH || path.join(process.cwd(), "data", "bigmoney.db");
}

function openSqliteSource(): { source: MigrationSource; close: () => void } {
  const db = new DatabaseSync(resolveSqlitePath(), { readOnly: true });
  const source: MigrationSource = {
    countRows: (table) => {
      const row = db.prepare(`SELECT COUNT(*) as c FROM ${table}`).get() as { c: number };
      return row.c;
    },
    readRows: (table) => db.prepare(`SELECT * FROM ${table}`).all() as MigrationRow[],
  };
  return { source, close: () => db.close() };
}

function buildPostgresTarget(client: PostgresQueryable): MigrationTarget {
  return {
    countRows: async (table) => {
      const { rows } = await client.query<{ c: string }>(`SELECT COUNT(*)::text as c FROM ${table}`);
      return Number(rows[0]?.c ?? 0);
    },
    insertRows: async (table, columns, rows) => {
      for (const row of rows) {
        const placeholders = columns.map((_, i) => `$${i + 1}`).join(", ");
        const values = columns.map((c) => row[c] ?? null);
        await client.query(`INSERT INTO ${table} (${columns.join(", ")}) VALUES (${placeholders})`, values);
      }
    },
    updateSelfReferentialColumn: async (table, primaryKeyColumn, column, rows) => {
      for (const row of rows) {
        const value = row[column];
        if (value == null) continue;
        await client.query(`UPDATE ${table} SET ${column} = $1 WHERE ${primaryKeyColumn} = $2`, [value, row[primaryKeyColumn]]);
      }
    },
  };
}

async function main() {
  const execute = process.argv.includes("--execute");
  const { source, close } = openSqliteSource();

  try {
    console.log(`Reading local SQLite database at ${resolveSqlitePath()}`);
    console.log(`Mode: ${execute ? "EXECUTE (writes to PostgreSQL)" : "DRY RUN (read-only, no PostgreSQL connection made)"}`);
    console.log("");

    const report = buildDryRunReport(source);
    console.log("Table                          Source rows");
    console.log("------------------------------  -----------");
    for (const entry of report) {
      console.log(`${entry.table.padEnd(30)}  ${String(entry.sourceRowCount).padStart(11)}`);
    }
    console.log("");
    console.log("Sample row per non-empty table (sensitive columns redacted):");
    for (const entry of report) {
      if (entry.sampleRedactedRow) console.log(`  ${entry.table}: ${JSON.stringify(entry.sampleRedactedRow)}`);
    }

    if (!execute) {
      console.log("");
      console.log("Dry run complete -- no PostgreSQL connection was made and nothing was written.");
      console.log("Re-run with --execute (and DATABASE_URL set) to perform the real migration.");
      return;
    }

    if (!process.env.DATABASE_URL) {
      throw new Error("--execute requires DATABASE_URL to be set (the target PostgreSQL database).");
    }

    console.log("");
    console.log("Applying any pending PostgreSQL migrations to the target database...");
    const pool = getPostgresPool();
    const migrationResult = await runPostgresMigrations(pool);
    console.log(`  applied: ${migrationResult.applied.join(", ") || "(none -- already up to date)"}`);

    console.log("");
    console.log("Migrating data...");
    const target = buildPostgresTarget(pool);
    const results = await runDataMigration(source, target);
    for (const r of results) {
      console.log(`  ${r.table.padEnd(30)} ${r.status.padEnd(24)} inserted=${r.rowsInserted} source=${r.sourceRowCount} targetAfter=${r.targetRowCountAfter}`);
    }
    console.log("");
    console.log(`Migration complete. ${results.filter((r) => r.status === "MIGRATED").length}/${MIGRATION_TABLES.length} tables migrated.`);
  } finally {
    close();
  }
}

main().catch((err) => {
  console.error("Migration failed:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
