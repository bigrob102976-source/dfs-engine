import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAdminApi: vi.fn(),
}));
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { requireAdminApi } = await import("@/lib/auth/guards");
const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createSavedLineup } = await import("@/lib/db/nflSavedLineups");
const { POST } = await import("../route");

const USER = { id: "user-1", email: "admin@example.com", role: "ADMIN" };

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(USER);
  vi.clearAllMocks();
});

describe("POST /api/nfl/export", () => {
  it("400s with no lineupIds", async () => {
    const res = await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: [] }) }));
    expect(res.status).toBe(400);
  });

  it("404s for an unknown lineup id, never calls Python", async () => {
    const res = await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: ["nope"] }) }));
    expect(res.status).toBe(404);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("404s for another user's lineup -- never exports someone else's real lineup", async () => {
    const row = await createSavedLineup({ userId: "someone-else", draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection", stackConfigJson: "{}", slotsJson: "[]" });
    const res = await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: [row.id] }) }));
    expect(res.status).toBe(404);
  });

  it("exports the owner's real saved lineup via the Python bridge", async () => {
    const row = await createSavedLineup({ userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection", stackConfigJson: "{}", slotsJson: "[]" });
    mockPythonSuccess({ csv: "QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n", lineup_count: 1, used_template: false });

    const res = await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: [row.id] }) }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.lineup_count).toBe(1);

    const [script, args] = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(script).toBe("scripts/nfl_dashboard_export.py");
    const payload = JSON.parse(args[0]);
    expect(payload.savedLineups[0].lineup_id).toBe(row.id);
    expect(payload.template).toBeUndefined();
  });

  it("forwards a real user-supplied template", async () => {
    const row = await createSavedLineup({ userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection", stackConfigJson: "{}", slotsJson: "[]" });
    mockPythonSuccess({ csv: "Entry ID,QB\n1,\n", lineup_count: 1, used_template: true });

    await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: [row.id], template: "Entry ID,QB\n1,\n" }) }));
    const payload = JSON.parse((runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1][0]);
    expect(payload.template).toBe("Entry ID,QB\n1,\n");
  });

  it("surfaces a real Python export error as 422", async () => {
    const row = await createSavedLineup({ userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection", stackConfigJson: "{}", slotsJson: "[]" });
    mockPythonSuccess({ error: "Saved lineup is missing slot 'DST'.", error_type: "LineupExportError" });

    const res = await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ lineupIds: [row.id] }) }));
    expect(res.status).toBe(422);
  });
});
