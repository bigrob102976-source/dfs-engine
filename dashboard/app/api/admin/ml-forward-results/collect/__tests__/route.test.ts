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
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/admin/ml-forward-results/collect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

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
    exitCode: 0, stdout: JSON.stringify({ status: "partial", date: "2026-08-22", slate_id: "dkunofficial-152547", games_final: 0 }), stderr: "", command: [],
  });
});

describe("POST /api/admin/ml-forward-results/collect", () => {
  it("rejects a MEMBER with 403", async () => {
    await loginAsMember();
    const res = await POST(req({ date: "2026-08-22", slateId: "dkunofficial-152547" }));
    expect(res.status).toBe(403);
    expect(mockRunPythonScript).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request with 401", async () => {
    const res = await POST(req({ date: "2026-08-22", slateId: "dkunofficial-152547" }));
    expect(res.status).toBe(401);
  });

  it("rejects a missing slateId with 400", async () => {
    await loginAsAdmin();
    const res = await POST(req({ date: "2026-08-22" }));
    expect(res.status).toBe(400);
    expect(mockRunPythonScript).not.toHaveBeenCalled();
  });

  it("an ADMIN can trigger collection and gets back the parsed status", async () => {
    await loginAsAdmin();
    const res = await POST(req({ date: "2026-08-22", slateId: "dkunofficial-152547" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status.slate_id).toBe("dkunofficial-152547");
    expect(mockRunPythonScript).toHaveBeenCalledWith("scripts/collect_ml_forward_results.py", ["--date", "2026-08-22", "--slate-id", "dkunofficial-152547"]);
  });

  it("returns 502 with the script's error output when collection fails unexpectedly", async () => {
    await loginAsAdmin();
    mockRunPythonScript.mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await POST(req({ date: "2026-08-22", slateId: "dkunofficial-152547" }));
    expect(res.status).toBe(502);
  });
});
