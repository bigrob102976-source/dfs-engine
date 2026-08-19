import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let originalEnv: Record<string, string | undefined>;

beforeEach(() => {
  originalEnv = {
    NODE_ENV: process.env.NODE_ENV,
    DATABASE_URL: process.env.DATABASE_URL,
    ALLOW_SQLITE_IN_PRODUCTION: process.env.ALLOW_SQLITE_IN_PRODUCTION,
    BIGMONEY_DB_PATH: process.env.BIGMONEY_DB_PATH,
  };
});

afterEach(() => {
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete (process.env as Record<string, string | undefined>)[key];
    else process.env[key] = value;
  }
  vi.resetModules();
});

describe("getDb() production guard (Milestone 30)", () => {
  it("throws when DATABASE_URL (Postgres) is configured -- this accessor is SQLite-only", async () => {
    vi.resetModules(); // fresh module instance -> dbInstance singleton starts null
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    process.env.DATABASE_URL = "postgres://user:pass@host:5432/db";
    const { getDb } = await import("../client");
    expect(() => getDb()).toThrow(/SQLite-only accessor/);
  });

  it("throws fail-closed when production has neither DATABASE_URL nor the override", async () => {
    vi.resetModules();
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    delete process.env.DATABASE_URL;
    delete process.env.ALLOW_SQLITE_IN_PRODUCTION;
    const { getDb } = await import("../client");
    expect(() => getDb()).toThrow(/DATABASE_URL is required in production/);
  });

  it("proceeds normally with the explicit ALLOW_SQLITE_IN_PRODUCTION override", async () => {
    vi.resetModules();
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    delete process.env.DATABASE_URL;
    process.env.ALLOW_SQLITE_IN_PRODUCTION = "true";
    process.env.BIGMONEY_DB_PATH = ":memory:";
    const { getDb } = await import("../client");
    expect(() => getDb()).not.toThrow();
  });

  it("development with no DATABASE_URL never throws -- unaffected local dev behavior", async () => {
    vi.resetModules();
    (process.env as Record<string, string | undefined>).NODE_ENV = "development";
    delete process.env.DATABASE_URL;
    process.env.BIGMONEY_DB_PATH = ":memory:";
    const { getDb } = await import("../client");
    expect(() => getDb()).not.toThrow();
  });
});
