import { beforeEach, describe, expect, it, vi } from "vitest";

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
const { POST: validateRoute } = await import("../validate/route");
const { POST: importRoute } = await import("../import/route");
const { POST: deactivateRoute } = await import("../deactivate/route");

// NOTE: this vitest suite runs under jsdom (vitest.config.ts), whose
// Request/FormData/File implementation does not reliably round-trip a
// real multipart body through request.formData() (a known jsdom fetch-
// polyfill gap, not specific to this route) -- see
// app/api/dfs-salaries/__tests__/accessControl.test.ts's own precedent
// for the SAME workaround: assert auth-gate status codes only here
// (401/403, which return before formData() is ever called), and cover
// the real CSV/canonical/collision/deactivate BEHAVIOR in
// lib/__tests__/adminCsvImport.test.ts instead, which calls the
// underlying lib/adminCsvImport.ts functions directly with plain
// Buffer/string arguments -- no Request/FormData involved, so no jsdom
// limitation to work around.

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

function emptyPostRequest(url: string): Request {
  return new Request(url, { method: "POST" });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("BREAK-GLASS ADMIN CSV UPLOAD -- Phase 10 access control (rules #2/#7/#10)", () => {
  it("validate: 401s with no session", async () => {
    const res = await validateRoute(emptyPostRequest("http://localhost/api/admin/slate-import/validate"));
    expect(res.status).toBe(401);
  });

  it("validate: 403s for a logged-in MEMBER -- members must never validate/preview a CSV import", async () => {
    await loginAsMember();
    const res = await validateRoute(emptyPostRequest("http://localhost/api/admin/slate-import/validate"));
    expect(res.status).toBe(403);
  });

  it("validate: an ADMIN is authorized to reach the real handler (never blocked by the guard)", async () => {
    await loginAsAdmin();
    const res = await validateRoute(emptyPostRequest("http://localhost/api/admin/slate-import/validate"));
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });

  it("import: 401s with no session", async () => {
    const res = await importRoute(emptyPostRequest("http://localhost/api/admin/slate-import/import"));
    expect(res.status).toBe(401);
  });

  it("import: 403s for a logged-in MEMBER -- members must never import a slate", async () => {
    await loginAsMember();
    const res = await importRoute(emptyPostRequest("http://localhost/api/admin/slate-import/import"));
    expect(res.status).toBe(403);
  });

  it("import: an ADMIN is authorized to reach the real handler (never blocked by the guard)", async () => {
    await loginAsAdmin();
    const res = await importRoute(emptyPostRequest("http://localhost/api/admin/slate-import/import"));
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });

  it("deactivate: 401s with no session", async () => {
    const res = await deactivateRoute(emptyPostRequest("http://localhost/api/admin/slate-import/deactivate"));
    expect(res.status).toBe(401);
  });

  it("deactivate: 403s for a logged-in MEMBER", async () => {
    await loginAsMember();
    const res = await deactivateRoute(emptyPostRequest("http://localhost/api/admin/slate-import/deactivate"));
    expect(res.status).toBe(403);
  });

  it("deactivate: an ADMIN is authorized to reach the real handler (never blocked by the guard)", async () => {
    await loginAsAdmin();
    const res = await deactivateRoute(
      new Request("http://localhost/api/admin/slate-import/deactivate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ internalSlateId: "s1" }),
      }),
    );
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });
});
