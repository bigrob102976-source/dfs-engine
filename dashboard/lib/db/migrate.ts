import fs from "node:fs";
import path from "node:path";
import type { DatabaseSync } from "node:sqlite";

// Resolved from process.cwd() (the Next.js project root at server
// runtime), NOT __dirname -- Next's bundler (webpack/Turbopack) rewrites
// __dirname to a synthetic build-time path (e.g. "C:\ROOT\lib\db") that
// doesn't exist on disk at request time, which only surfaces once real
// HTTP traffic hits a Route Handler (Vitest never bundles this code, so
// it never caught it). process.cwd() is how lib/db/client.ts already
// resolves the DB file path itself, so this stays consistent with that.
const MIGRATIONS_DIR = path.join(process.cwd(), "lib", "db", "migrations");

/** Applies every `lib/db/migrations/*.sql` file (sorted by filename, so
 * `0001_`/`0002_`/... always run in order) that isn't already recorded
 * in `schema_migrations`, each inside its own transaction. Safe to call
 * on every process start -- a fully-migrated database is a fast no-op
 * (one SELECT per migration file). */
export function runMigrations(db: DatabaseSync): void {
  db.exec(
    "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
  );

  const applied = new Set(
    db.prepare("SELECT filename FROM schema_migrations").all().map((row) => row.filename as string),
  );

  const files = fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((name) => name.endsWith(".sql"))
    .sort();

  for (const filename of files) {
    if (applied.has(filename)) continue;
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, filename), "utf-8");
    db.exec("BEGIN");
    try {
      db.exec(sql);
      db.prepare("INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)").run(
        filename,
        new Date().toISOString(),
      );
      db.exec("COMMIT");
    } catch (err) {
      db.exec("ROLLBACK");
      throw new Error(`Migration ${filename} failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}
