import type { Pool } from "pg";

import type { PostgresQueryable } from "./postgresClient";
import type { RunResult, SqlExecutor } from "./sqlExecutor";
import { toPostgresPlaceholders } from "./sqlExecutor";

/** Wraps a real `pg.Pool`/`pg.PoolClient` (or, in tests, a lightweight
 * fake satisfying PostgresQueryable -- see lib/db/postgresClient.ts's own
 * docstring for why that interface exists) behind the backend-neutral
 * SqlExecutor interface every query module talks to.
 *
 * Constructed two ways:
 *   - `new PostgresExecutor(pool, pool)` -- the top-level, process-wide
 *     instance (see lib/db/executor.ts). Passing the real Pool as BOTH
 *     `client` and `pool` lets ordinary (non-transactional) queries use
 *     the pool directly (any available connection), while transaction()
 *     checks out one dedicated connection for the duration of the
 *     callback.
 *   - `new PostgresExecutor(poolClient)` -- what transaction() itself
 *     builds internally, and what a test's fake PostgresQueryable is
 *     wrapped in. No `pool` means transaction() has no second connection
 *     to check out, so a nested transaction() call reuses this same
 *     connection/executor instead (mirrors SqliteExecutor's identical
 *     reentrancy rule). */
export class PostgresExecutor implements SqlExecutor {
  readonly backend = "postgres" as const;

  constructor(
    private readonly client: PostgresQueryable,
    private readonly pool?: Pool,
  ) {}

  async get<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T | undefined> {
    const { rows } = await this.client.query<T & Record<string, unknown>>(toPostgresPlaceholders(sql), params);
    return rows[0] as T | undefined;
  }

  async all<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
    const { rows } = await this.client.query<T & Record<string, unknown>>(toPostgresPlaceholders(sql), params);
    return rows as T[];
  }

  async run(sql: string, params: unknown[] = []): Promise<RunResult> {
    const result = await this.client.query(toPostgresPlaceholders(sql), params);
    // The real pg Pool/PoolClient's QueryResult also carries `rowCount`
    // (not part of the minimal PostgresQueryable interface, which only
    // promises `rows` -- see postgresClient.ts's docstring on why that
    // interface stays deliberately small). Fall back to rows.length for
    // a test fake that only ever returns `{ rows }`.
    const rowCount = (result as { rowCount?: number | null }).rowCount;
    return { changes: rowCount ?? result.rows.length };
  }

  async transaction<T>(fn: (tx: SqlExecutor) => Promise<T>): Promise<T> {
    if (!this.pool) {
      return fn(this);
    }
    const connection = await this.pool.connect();
    const txExecutor = new PostgresExecutor(connection);
    try {
      await connection.query("BEGIN");
      const result = await fn(txExecutor);
      await connection.query("COMMIT");
      return result;
    } catch (err) {
      await connection.query("ROLLBACK");
      throw err;
    } finally {
      connection.release();
    }
  }
}
