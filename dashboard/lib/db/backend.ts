// Milestone 30: database backend SELECTION -- the decision of "which
// database should this process talk to", kept completely separate from
// HOW to talk to it (lib/db/client.ts for SQLite, lib/db/postgresClient.ts
// for Postgres). This separation is what makes the decision itself
// fully unit-testable without a real Postgres server: resolveDbBackend()
// only ever reads process.env and lib/env.ts's environment detection.

import { isProduction } from "../env";

export type DbBackendKind = "sqlite" | "postgres";

export interface DbBackendDecision {
  kind: DbBackendKind;
  reason: string;
}

/** Escape hatch matching this project's existing "never silently fall
 * back... unless explicitly permitted by a safe configuration" pattern
 * (Mock Mode, etc.) -- lets a genuinely single-instance production
 * deployment (e.g. an early private beta on one box) opt into SQLite
 * on purpose, loudly, rather than by omission. */
const ALLOW_SQLITE_IN_PRODUCTION_FLAG = "ALLOW_SQLITE_IN_PRODUCTION";

export class ProductionDatabaseNotConfiguredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProductionDatabaseNotConfiguredError";
  }
}

/** Fail-closed: in production, a missing DATABASE_URL throws rather
 * than silently defaulting to local (per-instance, non-shared) SQLite
 * -- see this milestone's "PRODUCTION SQLITE GUARD" requirement. In
 * development/test, DATABASE_URL is entirely optional; its absence is
 * the normal, expected local-dev state. */
export function resolveDbBackend(): DbBackendDecision {
  const databaseUrl = process.env.DATABASE_URL;
  if (databaseUrl) {
    return { kind: "postgres", reason: "DATABASE_URL is configured." };
  }

  if (isProduction()) {
    if (process.env[ALLOW_SQLITE_IN_PRODUCTION_FLAG] === "true") {
      return {
        kind: "sqlite",
        reason: `DATABASE_URL is not set, but ${ALLOW_SQLITE_IN_PRODUCTION_FLAG}=true explicitly permits local SQLite in production.`,
      };
    }
    throw new ProductionDatabaseNotConfiguredError(
      "DATABASE_URL is required in production (a shared PostgreSQL database) -- refusing to silently fall back to " +
        "local SQLite, which would give separate app instances separate, disconnected membership databases. " +
        `Set DATABASE_URL, or explicitly set ${ALLOW_SQLITE_IN_PRODUCTION_FLAG}=true if you understand the risk ` +
        "(e.g. a genuinely single-instance early deployment).",
    );
  }

  return { kind: "sqlite", reason: "No DATABASE_URL configured; using local SQLite for development." };
}
