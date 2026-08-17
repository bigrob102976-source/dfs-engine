import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

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

/** Lazy singleton -- the database is opened (and migrated) on first
 * use, not at module load, so importing this module has no side
 * effects until a query actually runs. */
export function getDb(): DatabaseSync {
  if (!dbInstance) {
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
