import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetDbForTests } from "../../../../lib/db/client";
import { __resetExecutorForTests } from "../../../../lib/db/executor";
import { __resetStorageForTests } from "../../../../lib/storage/getStorage";
import { GET } from "../route";

const SENSITIVE_KEY_PATTERN = /password|token|secret|api[_-]?key|authorization|cookie|credential|database_url|dsn/i;

function assertNoSensitiveFields(value: unknown, path = "body"): void {
  if (value === null || typeof value !== "object") return;
  for (const [key, v] of Object.entries(value as Record<string, unknown>)) {
    expect(SENSITIVE_KEY_PATTERN.test(key), `${path}.${key} looks secret-shaped`).toBe(false);
    if (typeof v === "string") {
      // No filesystem paths, no SQL, no stack traces -- a stray absolute
      // path or a "at Object.<anonymous>" stack frame is the clearest
      // signal something internal leaked into a public response.
      expect(v, `${path}.${key} looks like a filesystem path`).not.toMatch(/^[A-Za-z]:\\|^\//);
      expect(v, `${path}.${key} looks like a stack trace`).not.toMatch(/\n\s*at /);
      expect(v, `${path}.${key} looks like a SQL statement`).not.toMatch(/\bSELECT\b|\bINSERT\b|\bUPDATE\b.*\bWHERE\b/i);
    }
    if (typeof v === "object") assertNoSensitiveFields(v, `${path}.${key}`);
  }
}

describe("GET /api/health", () => {
  beforeEach(() => {
    __resetDbForTests();
    __resetExecutorForTests();
    __resetStorageForTests();
  });

  it("is reachable and reports healthy with only sanitized database/storage fields, local dev (SQLite + local disk)", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.status).toBe("healthy");
    expect(body.database).toEqual({ status: "healthy", backend: "sqlite" });
    expect(body.storage).toEqual({ status: "healthy", backend: "local" });
    expect(typeof body.version).toBe("string");
    expect(typeof body.timestamp).toBe("string");
    expect(Number.isNaN(new Date(body.timestamp).getTime())).toBe(false);

    // Exactly this shape -- nothing extra snuck in.
    expect(Object.keys(body).sort()).toEqual(["database", "status", "storage", "timestamp", "version"]);
    expect(Object.keys(body.database).sort()).toEqual(["backend", "status"]);
    expect(Object.keys(body.storage).sort()).toEqual(["backend", "status"]);
  });

  it("never exposes a credential, filesystem path, SQL, or stack trace in the response, whatever the underlying status", async () => {
    const res = await GET();
    const body = await res.json();
    assertNoSensitiveFields(body);
  });
});

// Isolated in its own describe block using vi.doMock (not hoisted, so it
// only affects THIS test's dynamic re-import of the route) -- proves the
// route's status-mapping logic (unhealthy dependency -> 503, still
// sanitized) without needing to force a real Postgres/S3 outage.
describe("GET /api/health -- unhealthy dependency mapping", () => {
  beforeEach(() => {
    // The FIRST describe block's top-level `import { GET } from "../route"`
    // caches route.ts (and its static systemReadiness import) before any
    // vi.doMock in this block ever runs -- reset first so every test here
    // gets a genuinely fresh module graph bound to ITS OWN mock, not
    // whichever real/mocked systemReadiness happened to be cached last.
    vi.resetModules();
  });

  afterEach(() => {
    vi.doUnmock("../../../../lib/systemReadiness");
    vi.resetModules();
  });

  it("returns 503 (not 200) when the database is reported unhealthy, still with a sanitized body", async () => {
    vi.doMock("../../../../lib/systemReadiness", () => ({
      getDatabaseReadiness: async () => ({ kind: "postgres", status: "ERROR", schemaReady: false, detail: "connection refused at db.internal:5432" }),
      getObjectStorageReadiness: async () => ({ backend: "local", status: "CONNECTED", detail: "Local disk." }),
    }));
    const { GET: GetWithMockedReadiness } = await import("../route");

    const res = await GetWithMockedReadiness();
    const body = await res.json();
    expect(res.status).toBe(503);
    expect(body.status).toBe("unhealthy");
    expect(body.database).toEqual({ status: "unhealthy", backend: "postgres" });
    expect(body.storage).toEqual({ status: "healthy", backend: "local" });
    assertNoSensitiveFields(body);
    expect(JSON.stringify(body)).not.toContain("db.internal"); // the raw `detail` string never reaches the response
  });

  it("returns 503 when storage is reported unhealthy even though the database is fine", async () => {
    vi.doMock("../../../../lib/systemReadiness", () => ({
      getDatabaseReadiness: async () => ({ kind: "sqlite", status: "CONNECTED", schemaReady: true, detail: "Local SQLite database." }),
      getObjectStorageReadiness: async () => ({ backend: "object", status: "ERROR", detail: "AccessDenied: invalid credentials for bucket bigmoney-artifacts" }),
    }));
    const { GET: GetWithMockedReadiness } = await import("../route");

    const res = await GetWithMockedReadiness();
    const body = await res.json();
    expect(res.status).toBe(503);
    expect(body.status).toBe("unhealthy");
    expect(body.storage).toEqual({ status: "unhealthy", backend: "object" });
    assertNoSensitiveFields(body);
    expect(JSON.stringify(body)).not.toContain("AccessDenied");
    expect(JSON.stringify(body)).not.toContain("bigmoney-artifacts");
  });
});
