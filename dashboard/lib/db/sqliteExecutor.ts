import type { DatabaseSync } from "node:sqlite";

import type { RunResult, SqlExecutor } from "./sqlExecutor";

/** Wraps a node:sqlite DatabaseSync (already fully migrated -- see
 * lib/db/client.ts::getDb()) behind the backend-neutral SqlExecutor
 * interface. Every method is `async` only in its signature -- node:sqlite
 * is synchronous, so there's no real I/O to await here; this keeps every
 * query module's call sites uniform (`await executor.get(...)`)
 * regardless of which backend is actually selected at runtime. */
export class SqliteExecutor implements SqlExecutor {
  readonly backend = "sqlite" as const;

  private inTransaction = false;

  constructor(private readonly db: DatabaseSync) {}

  async get<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T | undefined> {
    const row = this.db.prepare(sql).get(...(params as never[]));
    return row as T | undefined;
  }

  async all<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
    return this.db.prepare(sql).all(...(params as never[])) as T[];
  }

  async run(sql: string, params: unknown[] = []): Promise<RunResult> {
    const result = this.db.prepare(sql).run(...(params as never[]));
    return { changes: Number(result.changes) };
  }

  /** node:sqlite has no SAVEPOINT support exposed through this thin a
   * wrapper -- a transaction() call nested inside an already-open one
   * (mirrors PostgresExecutor's identical reentrancy rule) just reuses
   * the same connection/transaction rather than attempting a nested
   * BEGIN, which SQLite would reject. */
  async transaction<T>(fn: (tx: SqlExecutor) => Promise<T>): Promise<T> {
    if (this.inTransaction) {
      return fn(this);
    }
    this.inTransaction = true;
    this.db.exec("BEGIN");
    try {
      const result = await fn(this);
      this.db.exec("COMMIT");
      return result;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    } finally {
      this.inTransaction = false;
    }
  }
}
