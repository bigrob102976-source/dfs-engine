import { afterEach, beforeEach, describe, expect, it } from "vitest";

let originalEnv: Record<string, string | undefined>;

beforeEach(() => {
  originalEnv = { NODE_ENV: process.env.NODE_ENV, DATABASE_URL: process.env.DATABASE_URL, ALLOW_SQLITE_IN_PRODUCTION: process.env.ALLOW_SQLITE_IN_PRODUCTION };
});

afterEach(() => {
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete (process.env as Record<string, string | undefined>)[key];
    else process.env[key] = value;
  }
});

describe("resolveDbBackend", () => {
  it("SQLite dev fallback: development with no DATABASE_URL resolves to sqlite", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "development";
    delete process.env.DATABASE_URL;
    const { resolveDbBackend } = await import("../backend");
    expect(resolveDbBackend()).toEqual({ kind: "sqlite", reason: expect.stringContaining("local SQLite for development") });
  });

  it("test environment with no DATABASE_URL resolves to sqlite", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "test";
    delete process.env.DATABASE_URL;
    const { resolveDbBackend } = await import("../backend");
    expect(resolveDbBackend().kind).toBe("sqlite");
  });

  it("Postgres production selection: DATABASE_URL configured resolves to postgres in any environment", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    process.env.DATABASE_URL = "postgres://user:pass@host:5432/db";
    const { resolveDbBackend } = await import("../backend");
    expect(resolveDbBackend()).toEqual({ kind: "postgres", reason: "DATABASE_URL is configured." });
  });

  it("DATABASE_URL configured in development also resolves to postgres (dev can opt into Postgres too)", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "development";
    process.env.DATABASE_URL = "postgres://user:pass@host:5432/db";
    const { resolveDbBackend } = await import("../backend");
    expect(resolveDbBackend().kind).toBe("postgres");
  });

  it("Production SQLite rejection: production with no DATABASE_URL and no override throws (fail closed)", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    delete process.env.DATABASE_URL;
    delete process.env.ALLOW_SQLITE_IN_PRODUCTION;
    const { resolveDbBackend, ProductionDatabaseNotConfiguredError } = await import("../backend");
    expect(() => resolveDbBackend()).toThrow(ProductionDatabaseNotConfiguredError);
    expect(() => resolveDbBackend()).toThrow(/DATABASE_URL is required in production/);
  });

  it("production with the explicit ALLOW_SQLITE_IN_PRODUCTION override resolves to sqlite instead of throwing", async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "production";
    delete process.env.DATABASE_URL;
    process.env.ALLOW_SQLITE_IN_PRODUCTION = "true";
    const { resolveDbBackend } = await import("../backend");
    const decision = resolveDbBackend();
    expect(decision.kind).toBe("sqlite");
    expect(decision.reason).toContain("explicitly permits local SQLite in production");
  });
});
