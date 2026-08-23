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

const mockRunPythonScript = vi.fn();
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: (...args: unknown[]) => mockRunPythonScript(...args),
  tail: (s: string) => s,
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET } = await import("../route");

async function loginAsMember() {
  const user = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(user.id, null);
}

async function loginAsAdmin() {
  const user = createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  updateUserRole(user.id, "ADMIN");
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  mockRunPythonScript.mockReset();
  mockRunPythonScript.mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify({ status: "ok", history: { total_slates_completed: 0, early_sample: true, early_sample_warning: "EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS", windows: {} } }), stderr: "", command: [],
  });
});

describe("GET /api/admin/ml-forward-results/history", () => {
  it("rejects a MEMBER with 403", async () => {
    await loginAsMember();
    const res = await GET();
    expect(res.status).toBe(403);
  });

  it("an ADMIN gets back the parsed cumulative history", async () => {
    await loginAsAdmin();
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.history.total_slates_completed).toBe(0);
    expect(body.history.early_sample).toBe(true);
  });

  it("returns 502 when the history script fails unexpectedly", async () => {
    await loginAsAdmin();
    mockRunPythonScript.mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await GET();
    expect(res.status).toBe(502);
  });
});
