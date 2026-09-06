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

function request(url: string) {
  return new Request(url);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/nfl/data", () => {
  it("returns 401 (via requireAuthApi) for an anonymous request, never runs Python", async () => {
    const unauthenticated = NextResponse.json({ error: "Authentication required." }, { status: 401 });
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(unauthenticated);

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=151307"));
    expect(res.status).toBe(401);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("400s on a missing/invalid draftGroupId", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "MEMBER" });
    const res = await GET(request("http://localhost/api/nfl/data"));
    expect(res.status).toBe(400);
  });

  it("an authenticated MEMBER (not admin) gets the real Python script's JSON on success", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "MEMBER" });
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({ draft_group_id: 151307, players: [] }),
      stderr: "",
      command: [],
    });

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=151307"));
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.draft_group_id).toBe(151307);
  });

  it("an ADMIN also still gets real data (admin access unaffected)", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "admin-1", role: "ADMIN" });
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({ draft_group_id: 151307, players: [] }),
      stderr: "",
      command: [],
    });

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=151307"));
    expect(res.status).toBe(200);
  });

  it("surfaces a real Python-reported error as 422, never fabricates data", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "MEMBER" });
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({ error: "DraftGroup 999 not found in current NFL universe." }),
      stderr: "",
      command: [],
    });

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=999"));
    expect(res.status).toBe(422);
  });

  it("502s when the Python process itself fails", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "MEMBER" });
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exitCode: 1,
      stdout: "",
      stderr: "Traceback...",
      command: [],
    });

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=424242"));
    expect(res.status).toBe(502);
  });
});
