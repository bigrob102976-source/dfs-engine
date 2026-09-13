import { NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAuthApi: vi.fn(),
}));
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { requireAuthApi } = await import("@/lib/auth/guards");
const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { __resetRateLimitForTests } = await import("@/lib/rateLimit");
const { POST } = await import("../route");

const USER = { id: "user-1", email: "member@example.com", role: "MEMBER" };

function request(body: unknown) {
  return new Request("http://localhost/api/nfl/optimize", { method: "POST", body: JSON.stringify(body) });
}

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

beforeEach(() => {
  __resetRateLimitForTests();
  (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(USER);
});
afterEach(() => {
  vi.clearAllMocks();
});

// Launch Blocker Sprint 1 (2026-09-13): reversed the prior "NFL public
// access, Phase 6" decision -- this is AUTHENTICATED COMPUTE now, the
// most expensive NFL endpoint (a real CP-SAT solve), matching
// /api/optimizer/build's (MLB's equivalent) auth requirement.
describe("POST /api/nfl/optimize -- AUTHENTICATED COMPUTE + M13 settings serialization", () => {
  it("returns 401 for an anonymous request, never calls Python", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      NextResponse.json({ error: "Authentication required." }, { status: 401 }),
    );
    const res = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
    expect(res.status).toBe(401);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("an authenticated request can build a lineup", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] });
    const res = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
    expect(res.status).toBe(200);
  });

  it("400s on a missing/invalid draftGroupId", async () => {
    const res = await POST(request({ numLineups: 1 }));
    expect(res.status).toBe(400);
  });

  it("passes the stack/exposure settings through to Python as a single JSON argv element", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "projection", lineups: [] });

    await POST(request({
      draftGroupId: 151307, numLineups: 5, mode: "leverage", locks: ["1"], excludes: ["2"],
      stack: { qbStackMode: "double", bringBackMode: "one", rbDstEnabled: true, maxPlayersPerTeam: 4, maxPlayersPerGame: 6 },
      maxExposure: { "3": 0.5 }, maxExposureDefault: 0.8, minExposure: { "4": 0.25 },
    }));

    expect(runPythonScript).toHaveBeenCalledTimes(1);
    const [scriptPath, args] = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(scriptPath).toBe("scripts/nfl_dashboard_optimize.py");
    expect(args[0]).toBe("151307");
    const settings = JSON.parse(args[1]);
    expect(settings).toEqual({
      numLineups: 5, mode: "leverage", locks: ["1"], excludes: ["2"],
      stack: { qbStackMode: "double", bringBackMode: "one", rbDstEnabled: true, maxPlayersPerTeam: 4, maxPlayersPerGame: 6 },
      maxExposure: { "3": 0.5 }, maxExposureDefault: 0.8, minExposure: { "4": 0.25 },
    });
  });

  it("sanitizes an unknown mode down to roster_feasibility rather than forwarding garbage", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] });

    await POST(request({ draftGroupId: 151307, numLineups: 1, mode: "not_a_real_mode" }));
    const args = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(args[1]).mode).toBe("roster_feasibility");
  });

  it("sanitizes an unknown qbStackMode down to off rather than forwarding garbage", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] });

    await POST(request({ draftGroupId: 151307, numLineups: 1, stack: { qbStackMode: "triple" } }));
    const args = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(args[1]).stack.qbStackMode).toBe("off");
  });

  it("drops out-of-range exposure fractions rather than forwarding invalid values", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] });

    await POST(request({ draftGroupId: 151307, numLineups: 1, maxExposure: { "1": 1.5, "2": 0.4 } }));
    const args = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(args[1]).maxExposure).toEqual({ "2": 0.4 });
  });

  it("caps numLineups at 50", async () => {
    mockPythonSuccess({ requested: 50, generated: 50, stopped_reason: null, mode: "roster_feasibility", lineups: [] });

    await POST(request({ draftGroupId: 151307, numLineups: 999 }));
    const args = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(args[1]).numLineups).toBe(50);
  });

  it("surfaces a real Python NflOptimizerConfigError as 422 with its error_type", async () => {
    mockPythonSuccess({ error: "Bring-back requires a QB stack.", error_type: "NflOptimizerConfigError" });

    const res = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
    const json = await res.json();
    expect(res.status).toBe(422);
    expect(json.error_type).toBe("NflOptimizerConfigError");
  });

  it("502s when the Python process itself fails", async () => {
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });

    const res = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
    expect(res.status).toBe(502);
  });

  it("429s once the per-IP rate limit is exceeded even for an authenticated caller -- auth alone is not the abuse guard", async () => {
    mockPythonSuccess({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] });
    for (let i = 0; i < 20; i++) {
      const res = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
      expect(res.status).toBe(200);
    }
    const blocked = await POST(request({ draftGroupId: 151307, numLineups: 1 }));
    expect(blocked.status).toBe(429);
    expect(runPythonScript).toHaveBeenCalledTimes(20);
  });
});
