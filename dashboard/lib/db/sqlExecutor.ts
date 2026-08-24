/** Milestone 33.1: the ONE query interface every lib/db/*.ts and
 * lib/jobs/*.ts module talks to -- decouples "what SQL to run" (business
 * logic, identical for both backends) from "how to run it" (SqliteExecutor
 * wraps node:sqlite's synchronous DatabaseSync; PostgresExecutor wraps
 * pg's async Pool/PoolClient). Every query module writes SQL using `?`
 * placeholders (the existing SQLite convention -- zero rewrite needed for
 * that backend); PostgresExecutor rewrites `?` -> `$1, $2, ...` internally
 * before handing the query to `pg`, so business logic is written ONCE.
 *
 * Backend-specific SQL text is still allowed (and used, sparingly) for
 * the handful of operations that genuinely need it -- e.g. SQLite's
 * built-in `rowid` has no Postgres equivalent, so a couple of query
 * modules branch on `executor.backend` for one query each. That is the
 * "SQL differences" axis this milestone's compatibility matrix documents;
 * it never means two separate business-logic implementations -- the
 * surrounding function, its validation, and its return shape stay one
 * shared implementation either way. */

export interface RunResult {
  /** Rows affected by an INSERT/UPDATE/DELETE. For an INSERT this is
   * normally 1 (or 0 if e.g. an ON CONFLICT DO NOTHING matched nothing)
   * -- deliberately never a rowid/lastInsertRowid, which has no portable
   * equivalent; callers that need the inserted row re-SELECT it by the
   * id they generated (crypto.randomUUID()) before the INSERT, same
   * pattern every query module already uses. */
  changes: number;
}

export interface SqlExecutor {
  readonly backend: "sqlite" | "postgres";
  get<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T | undefined>;
  all<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T[]>;
  run(sql: string, params?: unknown[]): Promise<RunResult>;
  /** Runs `fn` with an executor bound to a single connection/transaction
   * -- every call `fn` makes through the executor IT IS GIVEN commits or
   * rolls back together. Always use the executor passed into `fn`, never
   * the outer one that opened the transaction -- on Postgres those are
   * genuinely different connections, so mixing them would silently split
   * work across two transactions instead of one. */
  transaction<T>(fn: (tx: SqlExecutor) => Promise<T>): Promise<T>;
}

/** Rewrites `?` placeholders to Postgres's `$1, $2, ...` positional
 * syntax, skipping any `?` that appears inside a single-quoted string
 * literal (none of this codebase's SQL currently has one, but this stays
 * correct if that ever changes rather than silently miscounting a
 * literal `?` as a parameter). */
export function toPostgresPlaceholders(sql: string): string {
  let out = "";
  let inString = false;
  let paramIndex = 0;
  for (let i = 0; i < sql.length; i++) {
    const ch = sql[i];
    if (ch === "'") {
      inString = !inString;
      out += ch;
      continue;
    }
    if (ch === "?" && !inString) {
      paramIndex += 1;
      out += `$${paramIndex}`;
      continue;
    }
    out += ch;
  }
  return out;
}
