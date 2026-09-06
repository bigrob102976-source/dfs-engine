import { NextResponse } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAuthApi: vi.fn(),
}));
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { requireAuthApi } = await import("@/lib/auth/guards");
const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { GET } = await import("../route");

afterEach(() => {
  vi.clearAllMocks();
});

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

describe("GET /api/nfl/slates", () => {
  it("returns 401 for an anonymous request, never runs Python", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(NextResponse.json({ error: "Authentication required." }, { status: 401 }));
    const res = await GET();
    expect(res.status).toBe(401);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("an authenticated MEMBER (not admin) can discover real slates", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "MEMBER" });
    mockPythonSuccess({ slates: [{ draft_group_id: 151307, slate_date: "2026-09-13" }] });
    const res = await GET();
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.slates).toHaveLength(1);
  });

  it("an ADMIN can also discover real slates", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "admin-1", role: "ADMIN" });
    mockPythonSuccess({ slates: [] });
    const res = await GET();
    expect(res.status).toBe(200);
  });
});
