import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/nfl/export/public", { method: "POST", body: JSON.stringify(body) });
}

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

afterEach(() => {
  vi.clearAllMocks();
});

const ASSIGNMENTS = [
  { slot: "QB", draftkings_player_id: "1", name: "QB One" },
  { slot: "RB1", draftkings_player_id: "2", name: "RB One" },
];

describe("POST /api/nfl/export/public -- no auth required", () => {
  it("requires no authentication at all -- no guard is even imported", async () => {
    mockPythonSuccess({ csv: "QB,RB\n1,2\n", lineup_count: 1 });
    const res = await POST(req({ lineups: [{ assignments: ASSIGNMENTS }] }));
    expect(res.status).toBe(200);
  });

  it("400s with no lineups", async () => {
    const res = await POST(req({ lineups: [] }));
    expect(res.status).toBe(400);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("400s over the 50-lineup cap", async () => {
    const res = await POST(req({ lineups: Array.from({ length: 51 }, () => ({ assignments: ASSIGNMENTS })) }));
    expect(res.status).toBe(400);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("passes the caller-supplied lineups through to the stateless Python script", async () => {
    mockPythonSuccess({ csv: "QB,RB\n1,2\n", lineup_count: 1 });
    await POST(req({ lineups: [{ assignments: ASSIGNMENTS }] }));
    const [script, args] = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(script).toBe("scripts/nfl_public_export.py");
    const payload = JSON.parse(args[0]);
    expect(payload.lineups[0].assignments).toEqual(ASSIGNMENTS);
  });

  it("surfaces a real Python export error as 422", async () => {
    mockPythonSuccess({ error: "Lineup is missing slot 'DST'.", error_type: "LineupExportError" });
    const res = await POST(req({ lineups: [{ assignments: ASSIGNMENTS }] }));
    expect(res.status).toBe(422);
  });

  it("502s when the Python process itself fails", async () => {
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await POST(req({ lineups: [{ assignments: ASSIGNMENTS }] }));
    expect(res.status).toBe(502);
  });
});
