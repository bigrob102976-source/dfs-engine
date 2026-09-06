import { NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAuthApi: vi.fn(),
}));
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { requireAuthApi } = await import("@/lib/auth/guards");
const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createSavedLineup, getSavedLineupById } = await import("@/lib/db/nflSavedLineups");
const { POST } = await import("../route");

const USER = { id: "user-1", email: "member@example.com", role: "MEMBER" };

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(USER);
  vi.clearAllMocks();
});

async function makeLineup() {
  return createSavedLineup({
    userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
    stackConfigJson: "{}",
    slotsJson: JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "1", opponent: "MIA", game_id: "100", game_start_utc: "2026-09-13T17:00:00+00:00", projection_snapshot: 20 }]),
  });
}

describe("POST /api/nfl/lineups/[id]/late-swap", () => {
  it("returns 401 for an anonymous request, never calls Python", async () => {
    (requireAuthApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(NextResponse.json({ error: "Authentication required." }, { status: 401 }));
    const res = await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx("anything"));
    expect(res.status).toBe(401);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("404s for another user's lineup, never calls Python -- ownership is enforced before any solve", async () => {
    const row = await createSavedLineup({
      userId: "someone-else", draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
      stackConfigJson: "{}", slotsJson: JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "1" }]),
    });
    const res = await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx(row.id));
    expect(res.status).toBe(404);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("404s for an unknown lineup id, never calls Python", async () => {
    const res = await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx("nope"));
    expect(res.status).toBe(404);
    expect(runPythonScript).not.toHaveBeenCalled();
  });

  it("passes the saved lineup and settings to the real Python bridge", async () => {
    const row = await makeLineup();
    mockPythonSuccess({ locked_slots: [], unlocked_slots: ["QB"], changed_player_keys: [], fully_locked: false, lineup: null, error: null });

    await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ mode: "leverage" }) }), ctx(row.id));

    expect(runPythonScript).toHaveBeenCalledTimes(1);
    const [script, args] = (runPythonScript as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(script).toBe("scripts/nfl_dashboard_late_swap.py");
    expect(args[0]).toBe("151307");
    const payload = JSON.parse(args[1]);
    expect(payload.savedLineup.lineup_id).toBe(row.id);
    expect(payload.settings.mode).toBe("leverage");
  });

  it("does not persist by default (preview only)", async () => {
    const row = await makeLineup();
    mockPythonSuccess({
      locked_slots: [], unlocked_slots: ["QB"], changed_player_keys: ["2"], fully_locked: false,
      lineup: { assignments: [{ slot: "QB", draftkings_player_id: "2", name: "New QB", position: "QB", team: "BUF", salary: 6000, ceiling: null, projected_ownership: null }] },
      error: null,
    });

    await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx(row.id));
    const stillOriginal = await getSavedLineupById(row.id, USER.id);
    expect(JSON.parse(stillOriginal!.slots_json)[0].draftkings_player_id).toBe("1");
  });

  it("apply:true persists the swapped result onto the saved lineup", async () => {
    const row = await makeLineup();
    mockPythonSuccess({
      locked_slots: [], unlocked_slots: ["QB"], changed_player_keys: ["2"], fully_locked: false,
      lineup: { assignments: [{ slot: "QB", draftkings_player_id: "2", name: "New QB", position: "QB", team: "BUF", salary: 6000, ceiling: null, projected_ownership: null }] },
      error: null,
    });

    await POST(new Request("http://localhost", { method: "POST", body: JSON.stringify({ apply: true }) }), ctx(row.id));
    const updated = await getSavedLineupById(row.id, USER.id);
    expect(JSON.parse(updated!.slots_json)[0].draftkings_player_id).toBe("2");
  });

  it("surfaces a real Python error as 422", async () => {
    const row = await makeLineup();
    mockPythonSuccess({ error: "Saved lineup is for DraftGroup 151307, but the current pool is for a different DraftGroup entirely.", error_type: "LateSwapError" });

    const res = await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx(row.id));
    expect(res.status).toBe(422);
    const json = await res.json();
    expect(json.error_type).toBe("LateSwapError");
  });

  it("502s when the Python process itself fails", async () => {
    const row = await makeLineup();
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await POST(new Request("http://localhost", { method: "POST", body: "{}" }), ctx(row.id));
    expect(res.status).toBe(502);
  });
});
