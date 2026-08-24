import fs from "node:fs";
import path from "node:path";

import { Pool } from "pg";

// Milestone 30: PostgreSQL connection + migration runner. Kept
// deliberately separate from lib/db/client.ts (the existing SQLite
// accessor every current query module calls) -- see that file's own
// docstring for why they aren't merged into one accessor yet.

const MIGRATIONS_DIR = path.join(process.cwd(), "lib", "db", "migrations-postgres");

/** The minimal shape lib/db/*.ts query modules would need to run
 * against Postgres instead of SQLite -- deliberately just `query()`, so
 * both a real `pg.Pool`/`pg.PoolClient` AND a lightweight fake (for
 * tests that don't need a real Postgres server) satisfy it. */
export interface PostgresQueryable {
  query<T extends Record<string, unknown> = Record<string, unknown>>(
    sql: string,
    params?: unknown[],
  ): Promise<{ rows: T[] }>;
}

let pool: Pool | null = null;

/** Managed Postgres providers (Railway, Render, RDS, etc.) commonly
 * require TLS but present a certificate this process has no CA bundle
 * for -- `sslmode=require` (or no sslmode at all on most managed
 * providers' default connection strings) is handled the same way the
 * `pg` docs themselves recommend for that case. A connection string
 * that explicitly opts out (`sslmode=disable`) is honored, e.g. for a
 * local/self-hosted Postgres in development. */
function resolveSsl(connectionString: string): { rejectUnauthorized: boolean } | undefined {
  if (/sslmode=disable/i.test(connectionString)) return undefined;
  return { rejectUnauthorized: false };
}

/** Lazy singleton pool, mirroring lib/db/client.ts's lazy SQLite
 * singleton -- importing this module has no side effects until a query
 * actually runs. Throws if DATABASE_URL isn't set; callers should have
 * already gone through lib/db/backend.ts::resolveDbBackend() to know
 * Postgres was actually selected before calling this. */
export function getPostgresPool(): Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error("DATABASE_URL is not configured -- cannot open a PostgreSQL connection pool.");
    }
    pool = new Pool({ connectionString, ssl: resolveSsl(connectionString) });
  }
  return pool;
}

/** Test-only: replaces the pool singleton (e.g. with a real pool
 * pointed at a disposable test database, or left null to force the next
 * getPostgresPool() call to build a fresh one). Mirrors
 * lib/db/client.ts::__resetDbForTests()'s naming. */
export function __resetPostgresPoolForTests(): void {
  if (pool) {
    void pool.end().catch(() => {
      // already closed / never connected -- fine.
    });
  }
  pool = null;
}

export interface PostgresMigrationResult {
  applied: string[];
  alreadyApplied: string[];
}

/** Applies every lib/db/migrations-postgres/*.sql file (sorted by
 * filename, same "never reorder, never renumber" discipline as
 * lib/db/migrate.ts's SQLite runner) that isn't already recorded in
 * schema_migrations, each inside its own transaction. Accepts any
 * PostgresQueryable -- a real pg.Pool/PoolClient in production, or a
 * lightweight fake in tests that don't need (and per this milestone's
 * explicit instruction, must not fabricate) a real Postgres server. */
export async function runPostgresMigrations(client: PostgresQueryable): Promise<PostgresMigrationResult> {
  await client.query("CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL)");

  const { rows } = await client.query<{ filename: string }>("SELECT filename FROM schema_migrations");
  const alreadyApplied = rows.map((r) => r.filename);
  const appliedSet = new Set(alreadyApplied);

  const files = fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((name) => name.endsWith(".sql"))
    .sort();

  const applied: string[] = [];
  for (const filename of files) {
    if (appliedSet.has(filename)) continue;
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, filename), "utf-8");
    await client.query("BEGIN");
    try {
      await client.query(sql);
      await client.query("INSERT INTO schema_migrations (filename, applied_at) VALUES ($1, $2)", [filename, new Date().toISOString()]);
      await client.query("COMMIT");
      applied.push(filename);
    } catch (err) {
      await client.query("ROLLBACK");
      throw new Error(`PostgreSQL migration ${filename} failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return { applied, alreadyApplied };
}

/** Lists the *.sql migration filenames this runner would apply, without
 * connecting to anything -- used by the Admin System page's migration
 * status card and by the data-migration tool's dry-run mode. */
export function listPostgresMigrationFiles(): string[] {
  return fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((name) => name.endsWith(".sql"))
    .sort();
}

/** Real connectivity + readiness check -- used by /api/health's admin
 * readiness view and the Admin System page. Never throws; returns a
 * structured result so a connection failure renders as "ERROR", not a
 * 500. */
export async function checkPostgresConnection(): Promise<{ connected: boolean; error: string | null }> {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    return { connected: false, error: "DATABASE_URL is not configured." };
  }
  try {
    const p = getPostgresPool();
    await p.query("SELECT 1");
    return { connected: true, error: null };
  } catch (err) {
    return { connected: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export interface SchemaReadiness {
  ready: boolean;
  appliedCount: number;
  expectedCount: number;
  /** Filenames present on disk but not yet recorded in schema_migrations
   * -- never the SQL/table contents, only migration filenames, which are
   * safe to display (see this milestone's "never expose internal SQL"
   * requirement). */
  pending: string[];
}

/** Milestone 33.1: "is the schema actually ready," distinct from "can we
 * open a connection" (checkPostgresConnection above) -- a fresh Postgres
 * database connects fine and has zero tables. Compares
 * listPostgresMigrationFiles()'s on-disk list against schema_migrations'
 * applied rows; never applies anything itself (migrations are an
 * explicit, separate operator step -- see the production migration
 * command documented alongside this milestone's final report). Never
 * throws; a query failure (e.g. schema_migrations doesn't exist yet on a
 * brand-new database) is reported as ready:false, not a crash. */
export async function checkPostgresSchemaReadiness(client: PostgresQueryable = getPostgresPool()): Promise<SchemaReadiness> {
  const expected = listPostgresMigrationFiles();
  try {
    const { rows } = await client.query<{ filename: string }>("SELECT filename FROM schema_migrations");
    const applied = new Set(rows.map((r) => r.filename));
    const pending = expected.filter((f) => !applied.has(f));
    return { ready: pending.length === 0, appliedCount: applied.size, expectedCount: expected.length, pending };
  } catch {
    // schema_migrations itself doesn't exist yet -- a brand-new,
    // never-migrated database. Every expected migration is "pending."
    return { ready: false, appliedCount: 0, expectedCount: expected.length, pending: expected };
  }
}
