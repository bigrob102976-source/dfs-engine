import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined),
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET: getServingComparison } = await import("../route");

async function loginAsAdmin() {
  const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

async function loginAsMember() {
  const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

function req(url: string) {
  return new Request(url);
}

let tmpDir: string;

beforeEach(async () => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-servingcomparison-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  const { __resetStorageForTests } = await import("@/lib/storage/getStorage");
  __resetStorageForTests();
  // No cached legacy artifact exists in this fresh tmpDir, so listSlates()
  // falls through to scripts/list_dfs_slates.py -- faked here so this
  // access-control test never depends on a real Python subprocess.
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async () => ({
    exitCode: 0,
    stdout: JSON.stringify({
      status: "no_slate", reason: "no real slate for this test date", provider_name: null, provider_type: null,
      is_mock: false, is_connected: true, source: null, slates: [], slates_available: 0,
    }),
    stderr: "", command: [],
  }));
});

afterEach(async () => {
  const { __resetStorageForTests } = await import("@/lib/storage/getStorage");
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("@/lib/optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  __resetStorageForTests();
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("M5D: /api/admin/serving-comparison access control", () => {
  it("401s with no session", async () => {
    const res = await getServingComparison(req("http://localhost/api/admin/serving-comparison?date=2026-08-31"));
    expect(res.status).toBe(401);
  });

  it("403s for a logged-in MEMBER -- members must never see backend-comparison internals", async () => {
    await loginAsMember();
    const res = await getServingComparison(req("http://localhost/api/admin/serving-comparison?date=2026-08-31"));
    expect(res.status).toBe(403);
  });

  it("400s for an ADMIN missing the required date param", async () => {
    await loginAsAdmin();
    const res = await getServingComparison(req("http://localhost/api/admin/serving-comparison"));
    expect(res.status).toBe(400);
  });

  it("200s for an ADMIN and returns a real parity report shape", async () => {
    await loginAsAdmin();
    const res = await getServingComparison(req("http://localhost/api/admin/serving-comparison?date=2026-08-31"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.report).toBeDefined();
    expect(typeof body.report.slatesCompared).toBe("number");
  });

  it("never returns a database URL, Railway variable, API key, or storage credential", async () => {
    await loginAsAdmin();
    process.env.DATABASE_URL_TEST_SENTINEL = "postgres://sentinel-should-never-appear";
    const res = await getServingComparison(req("http://localhost/api/admin/serving-comparison?date=2026-08-31"));
    const bodyText = await res.text();
    for (const forbidden of ["DATABASE_URL", "RAILWAY_", "OBJECT_STORAGE_", "sentinel-should-never-appear", "AWS_SECRET", "STRIPE_SECRET"]) {
      expect(bodyText).not.toContain(forbidden);
    }
    delete process.env.DATABASE_URL_TEST_SENTINEL;
  });
});
