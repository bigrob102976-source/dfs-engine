import { NextResponse } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAdminApi: vi.fn(),
}));
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { requireAdminApi } = await import("@/lib/auth/guards");
const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { GET } = await import("../route");

function request(url: string) {
  return new Request(url);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/nfl/data", () => {
  it("returns 403 (via requireAdminApi) for a non-admin, never runs Python", async () => {
    const forbidden = NextResponse.json({ error: "Admin access required." }, { status: 403 });
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(forbidden);

    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=151307"));
    expect(res.status).toBe(403);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("400s on a missing/invalid draftGroupId", async () => {
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "ADMIN" });
    const res = await GET(request("http://localhost/api/nfl/data"));
    expect(res.status).toBe(400);
  });

  it("passes through the real Python script's JSON on success", async () => {
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "ADMIN" });
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

  it("surfaces a real Python-reported error as 422, never fabricates data", async () => {
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "ADMIN" });
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
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "u1", role: "ADMIN" });
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
