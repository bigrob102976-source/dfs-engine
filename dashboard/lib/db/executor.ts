import { resolveDbBackend } from "./backend";
import { getDb } from "./client";
import { getPostgresPool } from "./postgresClient";
import { PostgresExecutor } from "./postgresExecutor";
import { SqliteExecutor } from "./sqliteExecutor";
import type { SqlExecutor } from "./sqlExecutor";

let executorInstance: SqlExecutor | null = null;

/** Milestone 33.1: THE single entry point every lib/db/*.ts and
 * lib/jobs/*.ts query module calls -- replaces the old direct `getDb()`
 * calls (which only ever worked against SQLite; see lib/db/client.ts's
 * docstring on why that accessor still exists, unchanged, as the SQLite
 * *implementation detail* SqliteExecutor wraps).
 *
 * Resolves the backend via resolveDbBackend() (lib/db/backend.ts) exactly
 * once per process -- same lazy-singleton discipline as
 * getDb()/getPostgresPool() themselves. Never silently falls back: if
 * DATABASE_URL is configured, this ALWAYS returns a PostgresExecutor -- a
 * broken Postgres connection surfaces as a rejected query promise from
 * whatever query module called it, never a silent SQLite substitution.
 *
 * Deliberately does NOT apply Postgres migrations itself -- migrations
 * are an explicit, separate operator step (see
 * lib/db/postgresClient.ts::runPostgresMigrations and this milestone's
 * documented production migration command), never an implicit side
 * effect of the first query a request happens to make. (SQLite's
 * lib/db/client.ts::getDb() already applies its own migrations on open,
 * same as before this milestone -- that pre-existing, cheap, purely-local
 * behavior is intentionally left unchanged.) */
export function getExecutor(): SqlExecutor {
  if (!executorInstance) {
    const decision = resolveDbBackend();
    executorInstance =
      decision.kind === "postgres"
        ? new PostgresExecutor(getPostgresPool(), getPostgresPool())
        : new SqliteExecutor(getDb());
  }
  return executorInstance;
}

/** Test-only: forces the next getExecutor() call to rebuild from scratch.
 * Mirrors __resetDbForTests()/__resetPostgresPoolForTests()'s naming --
 * a SQLite test should call __resetDbForTests() (which already swaps in a
 * fresh in-memory database) and then this, so the rebuilt executor wraps
 * the fresh instance rather than a stale one left over from an earlier
 * test. */
export function __resetExecutorForTests(): void {
  executorInstance = null;
}

/** Test-only: injects a pre-built executor directly (e.g. a
 * PostgresExecutor wrapping an in-memory fake PostgresQueryable) so a
 * query module's business logic can be exercised against the Postgres
 * code path without a real Postgres server -- see lib/db/__tests__ for
 * the dual-backend contract tests this enables. */
export function __setExecutorForTests(executor: SqlExecutor): void {
  executorInstance = executor;
}
