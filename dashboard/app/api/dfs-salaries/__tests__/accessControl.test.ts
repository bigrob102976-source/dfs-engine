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
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST: uploadDkCsv } = await import("../upload/route");
const { POST: deleteDkCsv } = await import("../delete/route");
const { GET: listDkUploads } = await import("../uploads/route");

async function loginAsAdmin() {
  const admin = createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

async function loginAsMember() {
  const member = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

function uploadRequest(): Request {
  const form = new FormData();
  form.append("file", new File(["Position,Name,ID,Salary,Game Info,TeamAbbrev\n"], "DKSalaries.csv", { type: "text/csv" }));
  form.append("date", "2026-08-19");
  form.append("slateLabel", "Main");
  return new Request("http://localhost/api/dfs-salaries/upload", { method: "POST", body: form });
}

function deleteRequest(): Request {
  return new Request("http://localhost/api/dfs-salaries/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: "dfs_input/2026-08-19/uploaded_dk_slates/main_1.csv" }),
  });
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("DK salary upload/delete/list -- Milestone 29 admin-only access control", () => {
  it("upload: 401s with no session (member upload denial -- not logged in)", async () => {
    const res = await uploadDkCsv(uploadRequest());
    expect(res.status).toBe(401);
  });

  it("upload: 403s for a logged-in MEMBER -- members must never be able to upload a DK CSV", async () => {
    await loginAsMember();
    const res = await uploadDkCsv(uploadRequest());
    expect(res.status).toBe(403);
  });

  it("upload: an ADMIN is authorized to reach the real upload handler (never blocked by the guard)", async () => {
    await loginAsAdmin();
    const res = await uploadDkCsv(uploadRequest());
    // The guard passes an ADMIN through; the underlying Python upload
    // script then runs for real and reports its own format validation --
    // what matters here is that access control itself never rejected it.
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });

  it("delete: 403s for a MEMBER -- members must never be able to replace/remove the DK source file", async () => {
    await loginAsMember();
    const res = await deleteDkCsv(deleteRequest());
    expect(res.status).toBe(403);
  });

  it("delete: 401s with no session", async () => {
    const res = await deleteDkCsv(deleteRequest());
    expect(res.status).toBe(401);
  });

  it("uploads listing: 403s for a MEMBER", async () => {
    await loginAsMember();
    const res = await listDkUploads(new Request("http://localhost/api/dfs-salaries/uploads?date=2026-08-19"));
    expect(res.status).toBe(403);
  });
});
