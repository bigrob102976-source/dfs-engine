import { describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { SqliteExecutor } from "../sqliteExecutor";

// Milestone 33.1: transaction atomicity -- the multi-statement writes
// this milestone identified as needing it (publish version pointer +
// publish history, in lib/db/slateStatus.ts) go through
// SqlExecutor.transaction(). Tested here directly against the
// primitive itself, isolated from any one caller's business logic.

describe("SqliteExecutor.transaction", () => {
  it("commits all statements together on success", async () => {
    __resetDbForTests();
    const db = new SqliteExecutor(getDb());
    await db.run("INSERT INTO sports (code, name, status, sort_order) VALUES ('TXT', 'Test Sport', 'LIVE', 99)");

    await db.transaction(async (tx) => {
      await tx.run("UPDATE sports SET name = 'Updated' WHERE code = 'TXT'");
      await tx.run("UPDATE sports SET sort_order = 5 WHERE code = 'TXT'");
    });

    const row = await db.get<{ name: string; sort_order: number }>("SELECT * FROM sports WHERE code = 'TXT'");
    expect(row?.name).toBe("Updated");
    expect(row?.sort_order).toBe(5);
  });

  it("rolls back ALL statements together when a later one throws -- never a half-applied write", async () => {
    __resetDbForTests();
    const db = new SqliteExecutor(getDb());
    await db.run("INSERT INTO sports (code, name, status, sort_order) VALUES ('TXT', 'Original', 'LIVE', 1)");

    await expect(
      db.transaction(async (tx) => {
        await tx.run("UPDATE sports SET name = 'Should Not Stick' WHERE code = 'TXT'");
        throw new Error("simulated failure after the first write");
      }),
    ).rejects.toThrow("simulated failure");

    const row = await db.get<{ name: string }>("SELECT * FROM sports WHERE code = 'TXT'");
    expect(row?.name).toBe("Original"); // the UPDATE was rolled back, not left half-applied
  });

  it("a transaction() called from inside another transaction() reuses the same connection instead of nesting BEGIN", async () => {
    __resetDbForTests();
    const db = new SqliteExecutor(getDb());
    await db.run("INSERT INTO sports (code, name, status, sort_order) VALUES ('TXT', 'Original', 'LIVE', 1)");

    await db.transaction(async (tx) => {
      await tx.run("UPDATE sports SET sort_order = 10 WHERE code = 'TXT'");
      // Nested call -- must not throw "cannot start a transaction within a transaction".
      await tx.transaction(async (inner) => {
        await inner.run("UPDATE sports SET sort_order = 20 WHERE code = 'TXT'");
      });
    });

    const row = await db.get<{ sort_order: number }>("SELECT * FROM sports WHERE code = 'TXT'");
    expect(row?.sort_order).toBe(20);
  });
});
