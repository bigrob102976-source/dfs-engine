import { afterEach, beforeEach, describe, expect, it } from "vitest";

const ENV_KEYS = [
  "NODE_ENV",
  "OBJECT_STORAGE_ENDPOINT",
  "OBJECT_STORAGE_REGION",
  "OBJECT_STORAGE_BUCKET",
  "OBJECT_STORAGE_ACCESS_KEY",
  "OBJECT_STORAGE_SECRET_KEY",
  "ALLOW_LOCAL_STORAGE_IN_PRODUCTION",
] as const;

let originalEnv: Record<string, string | undefined>;

beforeEach(() => {
  originalEnv = Object.fromEntries(ENV_KEYS.map((k) => [k, process.env[k]]));
});

afterEach(() => {
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete (process.env as Record<string, string | undefined>)[key];
    else (process.env as Record<string, string | undefined>)[key] = value;
  }
});

function setEnv(key: string, value: string) {
  (process.env as Record<string, string | undefined>)[key] = value;
}

describe("resolveStorageBackend", () => {
  it("local disk fallback: development with no OBJECT_STORAGE_* vars resolves to local", async () => {
    setEnv("NODE_ENV", "development");
    for (const k of ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]) {
      delete (process.env as Record<string, string | undefined>)[k];
    }
    const { resolveStorageBackend } = await import("../backend");
    expect(resolveStorageBackend()).toEqual({ kind: "local", reason: expect.stringContaining("local disk for development") });
  });

  it("object storage selected when all four required vars are set, in any environment", async () => {
    setEnv("NODE_ENV", "production");
    setEnv("OBJECT_STORAGE_REGION", "auto");
    setEnv("OBJECT_STORAGE_BUCKET", "bigmoney-artifacts");
    setEnv("OBJECT_STORAGE_ACCESS_KEY", "AKIAFAKE");
    setEnv("OBJECT_STORAGE_SECRET_KEY", "fakeSecret");
    const { resolveStorageBackend } = await import("../backend");
    expect(resolveStorageBackend()).toEqual({ kind: "object", reason: expect.stringContaining("configured") });
  });

  it("fails closed: production with no object storage configured and no override throws", async () => {
    setEnv("NODE_ENV", "production");
    for (const k of ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY", "ALLOW_LOCAL_STORAGE_IN_PRODUCTION"]) {
      delete (process.env as Record<string, string | undefined>)[k];
    }
    const { resolveStorageBackend, ProductionStorageNotConfiguredError } = await import("../backend");
    expect(() => resolveStorageBackend()).toThrow(ProductionStorageNotConfiguredError);
    expect(() => resolveStorageBackend()).toThrow(/OBJECT_STORAGE_REGION[\s\S]*are required in production/);
  });

  it("production with the explicit ALLOW_LOCAL_STORAGE_IN_PRODUCTION override resolves to local instead of throwing", async () => {
    setEnv("NODE_ENV", "production");
    for (const k of ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]) {
      delete (process.env as Record<string, string | undefined>)[k];
    }
    setEnv("ALLOW_LOCAL_STORAGE_IN_PRODUCTION", "true");
    const { resolveStorageBackend } = await import("../backend");
    const decision = resolveStorageBackend();
    expect(decision.kind).toBe("local");
    expect(decision.reason).toContain("explicitly permits local disk in production");
  });

  it("a partially-configured object storage (missing one var) does not count as configured, and still fails closed in production", async () => {
    setEnv("NODE_ENV", "production");
    setEnv("OBJECT_STORAGE_REGION", "auto");
    setEnv("OBJECT_STORAGE_BUCKET", "bigmoney-artifacts");
    delete (process.env as Record<string, string | undefined>).OBJECT_STORAGE_ACCESS_KEY;
    delete (process.env as Record<string, string | undefined>).OBJECT_STORAGE_SECRET_KEY;
    delete (process.env as Record<string, string | undefined>).ALLOW_LOCAL_STORAGE_IN_PRODUCTION;
    const { resolveStorageBackend, ProductionStorageNotConfiguredError } = await import("../backend");
    expect(() => resolveStorageBackend()).toThrow(ProductionStorageNotConfiguredError);
  });
});
