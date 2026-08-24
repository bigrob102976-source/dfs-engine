import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Milestone 33.1: getExecutor() is the resolved production blocker --
// unlike the old getDb() (still SQLite-only by design, unchanged, see
// clientProductionGuard.test.ts), getExecutor() ACTUALLY returns a
// working PostgresExecutor when DATABASE_URL is configured, instead of
// throwing. This is the one behavioral contract this whole milestone
// exists to satisfy, so it gets its own direct test.

let originalEnv: Record<string, string | undefined>;

beforeEach(() => {
  originalEnv = {
    NODE_ENV: process.env.NODE_ENV,
    DATABASE_URL: process.env.DATABASE_URL,
    BIGMONEY_DB_PATH: process.env.BIGMONEY_DB_PATH,
  };
});

afterEach(async () => {
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete (process.env as Record<string, string | undefined>)[key];
    else process.env[key] = value;
  }
  const { __resetExecutorForTests } = await import("../executor");
  const { __resetPostgresPoolForTests } = await import("../postgresClient");
  __resetExecutorForTests();
  __resetPostgresPoolForTests();
});

describe("getExecutor", () => {
  it("returns a SqliteExecutor when no DATABASE_URL is configured (unchanged local dev behavior)", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "test";
    delete process.env.DATABASE_URL;
    process.env.BIGMONEY_DB_PATH = ":memory:";
    const { getExecutor, __resetExecutorForTests } = await import("../executor");
    __resetExecutorForTests();
    const db = getExecutor();
    expect(db.backend).toBe("sqlite");
  });

  it("returns a working PostgresExecutor when DATABASE_URL is configured -- the M33.0 blocker, resolved", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    process.env.DATABASE_URL = "postgres://user:pass@host:5432/db";
    const { getExecutor, __resetExecutorForTests } = await import("../executor");
    __resetExecutorForTests();
    const db = getExecutor();
    expect(db.backend).toBe("postgres");
    // Never throws just by resolving -- the old getDb() equivalent
    // ("lib/db/client.ts::getDb() is a SQLite-only accessor") is gone
    // for every query module, which now all call getExecutor() instead.
  });

  it("is a lazy singleton -- repeated calls return the same executor instance", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "test";
    delete process.env.DATABASE_URL;
    process.env.BIGMONEY_DB_PATH = ":memory:";
    const { getExecutor, __resetExecutorForTests } = await import("../executor");
    __resetExecutorForTests();
    expect(getExecutor()).toBe(getExecutor());
  });
});
