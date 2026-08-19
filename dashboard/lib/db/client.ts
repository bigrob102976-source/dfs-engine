import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import { resolveDbBackend } from "./backend";
import { runMigrations } from "./migrate";

// Milestone 21: the membership/admin/entitlements database. This is a
// Node-owned store, distinct from every Python-generated artifact
// directory -- it never lives under getArtifactRoot() (that function's
// own docstring is explicit: "this dashboard never writes into this
// tree -- it only reads"). Resolved relative to process.cwd(), which is
// always dashboard/ for every command this project's CLAUDE.md
// documents (npm run dev/build/start/test).
const DEFAULT_DB_PATH = path.join(process.cwd(), "data", "bigmoney.db");

function resolveDbPath(): string {
  return process.env.BIGMONEY_DB_PATH || DEFAULT_DB_PATH;
}

function openDatabase(location: string): DatabaseSync {
  if (location !== ":memory:") {
    fs.mkdirSync(path.dirname(location), { recursive: true });
  }
  const db = new DatabaseSync(location);
  db.exec("PRAGMA foreign_keys = ON");
  if (location !== ":memory:") {
    db.exec("PRAGMA journal_mode = WAL");
  }
  runMigrations(db);
  return db;
}

let dbInstance: DatabaseSync | null = null;

/** Milestone 30: this accessor only ever knows how to speak SQLite --
 * resolveDbBackend() (lib/db/backend.ts) is the single source of truth
 * for "which database should this process use", and getDb() defers to
 * it before ever touching disk:
 *   - decision "sqlite" (dev/test with no DATABASE_URL, or an explicit
 *     ALLOW_SQLITE_IN_PRODUCTION=true override) -> proceeds exactly as
 *     before, zero behavior change for local development.
 *   - decision "postgres" (DATABASE_URL is configured) -> throws. This
 *     accessor is SQLite-only; the 17 query modules under lib/db/*.ts
 *     that call getDb() have not yet been ported to the async Postgres
 *     adapter (lib/db/postgresClient.ts) -- that port is real, separate
 *     follow-up work (see DEPLOYMENT.md). Silently using local SQLite
 *     here even though a shared Postgres database was explicitly
 *     configured would be exactly the kind of silent, wrong fallback
 *     this milestone forbids -- so this fails loudly instead. */
export function getDb(): DatabaseSync {
  if (!dbInstance) {
    const backend = resolveDbBackend();
    if (backend.kind === "postgres") {
      throw new Error(
        "DATABASE_URL is configured for PostgreSQL, but lib/db/client.ts::getDb() is a SQLite-only accessor -- " +
          "the application's query layer has not yet been ported to lib/db/postgresClient.ts's Postgres adapter. " +
          "See DEPLOYMENT.md for what remains before this accessor can serve a production Postgres database.",
      );
    }
    dbInstance = openDatabase(resolveDbPath());
  }
  return dbInstance;
}

/** Test-only: swaps the singleton to a fresh in-memory database (fully
 * migrated) so every test file gets complete isolation from both the
 * real database file and every other test -- mirrors the
 * __setPythonRunnerForTests/__resetPythonRunnerForTests seam already
 * used in lib/orchestrator/pythonRunner.ts. */
export function __resetDbForTests(): DatabaseSync {
  if (dbInstance) {
    try {
      dbInstance.close();
    } catch {
      // already closed -- fine.
    }
  }
  dbInstance = openDatabase(":memory:");
  return dbInstance;
}
