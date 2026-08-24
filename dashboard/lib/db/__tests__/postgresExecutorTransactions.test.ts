import { describe, expect, it, vi } from "vitest";

import { PostgresExecutor } from "../postgresExecutor";
import type { PostgresQueryable } from "../postgresClient";

// Milestone 33.1: proves PostgresExecutor.transaction() checks out a
// SINGLE dedicated connection (never the shared pool) for the whole
// callback, issues real BEGIN/COMMIT/ROLLBACK, and always releases the
// connection back to the pool -- no real Postgres server required (this
// only tests the executor's own orchestration logic against a fake
// Pool/PoolClient pair, same discipline as postgresClient.test.ts).

function fakePoolAndClient(opts: { failOn?: string } = {}) {
  const calls: string[] = [];
  let released = false;
  const client: PostgresQueryable & { release: () => void } = {
    query: vi.fn(async (sql: string) => {
      calls.push(sql);
      if (opts.failOn && sql.includes(opts.failOn)) throw new Error("simulated query failure");
      return { rows: [] };
    }) as PostgresQueryable["query"],
    release: () => {
      released = true;
    },
  };
  const pool = {
    connect: vi.fn(async () => client),
  };
  return { pool: pool as unknown as import("pg").Pool, client, calls, wasReleased: () => released };
}

describe("PostgresExecutor.transaction", () => {
  it("checks out a connection, runs BEGIN before the callback and COMMIT after, then releases it", async () => {
    const { pool, calls, wasReleased } = fakePoolAndClient();
    const executor = new PostgresExecutor(pool as unknown as PostgresQueryable, pool);

    await executor.transaction(async (tx) => {
      await tx.run("UPDATE users SET role = ? WHERE id = ?", ["ADMIN", "u1"]);
    });

    expect(calls[0]).toBe("BEGIN");
    expect(calls[calls.length - 1]).toBe("COMMIT");
    expect(calls.some((c) => c.includes("UPDATE users"))).toBe(true);
    expect(wasReleased()).toBe(true);
  });

  it("issues ROLLBACK and still releases the connection when the callback throws", async () => {
    const { pool, calls, wasReleased } = fakePoolAndClient({ failOn: "UPDATE users" });
    const executor = new PostgresExecutor(pool as unknown as PostgresQueryable, pool);

    await expect(
      executor.transaction(async (tx) => {
        await tx.run("UPDATE users SET role = $1 WHERE id = $2", ["ADMIN", "u1"]);
      }),
    ).rejects.toThrow("simulated query failure");

    expect(calls).toContain("BEGIN");
    expect(calls).toContain("ROLLBACK");
    expect(calls).not.toContain("COMMIT");
    expect(wasReleased()).toBe(true);
  });

  it("every statement inside the callback runs on the SAME checked-out connection, not the pool", async () => {
    const { pool, client } = fakePoolAndClient();
    const executor = new PostgresExecutor(pool as unknown as PostgresQueryable, pool);

    await executor.transaction(async (tx) => {
      await tx.run("UPDATE a SET x = 1");
      await tx.run("UPDATE b SET y = 2");
    });

    // Both statements + BEGIN/COMMIT went through the one dedicated
    // client this transaction checked out -- never a second pool.connect().
    expect(pool.connect).toHaveBeenCalledTimes(1);
    expect((client.query as ReturnType<typeof vi.fn>).mock.calls.length).toBe(4); // BEGIN, 2 updates, COMMIT
  });

  it("a transaction() called without a pool (already inside another transaction) reuses the same executor instead of opening a second connection", async () => {
    const { client } = fakePoolAndClient();
    const txExecutor = new PostgresExecutor(client); // no `pool` -- mirrors what transaction() builds internally
    const result = await txExecutor.transaction(async (tx) => {
      await tx.run("UPDATE x SET y = 1");
      return "done";
    });
    expect(result).toBe("done");
  });
});
