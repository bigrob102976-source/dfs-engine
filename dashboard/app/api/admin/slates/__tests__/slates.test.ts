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
const { GET: getSlates } = await import("../route");

let tmpDir: string;
let originalRoot: string | undefined;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-admin-slates-api-"));
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("GET /api/admin/slates", () => {
  it("401s with no session", async () => {
    const res = await getSlates();
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await getSlates();
    expect(res.status).toBe(403);
  });

  it("returns real pipeline status for an ADMIN", async () => {
    const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const res = await getSlates();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.statuses.length).toBeGreaterThan(0);
    expect(body.statuses.every((s: { state: string }) => s.state === "missing")).toBe(true);
  });
});
