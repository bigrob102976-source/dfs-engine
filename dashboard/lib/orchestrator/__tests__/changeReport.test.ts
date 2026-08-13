import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { RunState, StepResult } from "../types";

let tmpDir: string;

function writeJson(filePath: string, data: unknown) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function stubStep(id: StepResult["id"], artifactPath: string | null): StepResult {
  return {
    id,
    label: id,
    status: artifactPath ? "ready" : "skipped",
    startedAt: null,
    finishedAt: null,
    message: null,
    artifactPath,
    command: null,
    stdoutTail: null,
    stderrTail: null,
  };
}

function stubRun(overrides: {
  runId: string;
  slateDate: string;
  status: RunState["status"];
  battersPath?: string | null;
  poolPath?: string | null;
  ownershipPath?: string | null;
  projectionLineupsPath?: string | null;
}): RunState {
  return {
    runId: overrides.runId,
    slateDate: overrides.slateDate,
    status: overrides.status,
    outcome: overrides.status === "completed" ? "ready" : null,
    startedAt: "2026-08-12T18:00:00Z",
    finishedAt: overrides.status === "completed" ? "2026-08-12T18:30:00Z" : null,
    currentStepId: null,
    steps: [
      stubStep("research", null),
      stubStep("pitchers", null),
      stubStep("batters", overrides.battersPath ?? null),
      stubStep("dfsSalaries", null),
      stubStep("playerPool", overrides.poolPath ?? null),
      stubStep("ownership", overrides.ownershipPath ?? null),
      stubStep("optimizer", null),
    ],
    slateOptions: null,
    summary:
      overrides.status === "completed"
        ? {
            slateDate: overrides.slateDate,
            mlbGames: null,
            dfsGames: null,
            postedLineups: null,
            missingLineups: null,
            pitcherCount: null,
            hitterCount: null,
            salaryCoveragePercent: null,
            positionCoveragePercent: null,
            dkEntries: null,
            matchedToMlb: null,
            unmatchedCount: null,
            rosterFeasibilityPass: null,
            ownershipReady: true,
            lineupCounts: { projection: 20, balanced: 20, leverage: 20 },
            lineupSetPaths: { projection: overrides.projectionLineupsPath ?? null, balanced: null, leverage: null },
            providerName: "mock_dev_provider",
            isMock: true,
            providerSource: "automatic_fallback",
            selectedSlateId: "mock-main",
          }
        : null,
    changeReport: null,
    error: null,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-changereport-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("buildChangeReport", () => {
  it("returns an explanatory empty report when there is no previous completed run", async () => {
    const { buildChangeReport } = await import("../changeReport");
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed" });
    const report = buildChangeReport(null, current);
    expect(report.previousRunId).toBeNull();
    expect(report.notes[0]).toMatch(/no prior completed refresh/i);
  });

  it("returns an explanatory empty report when the previous run was for a different date", async () => {
    const { buildChangeReport } = await import("../changeReport");
    const previous = stubRun({ runId: "run-1", slateDate: "2026-08-11", status: "completed" });
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed" });
    const report = buildChangeReport(previous, current);
    expect(report.previousRunId).toBeNull();
    expect(report.notes[0]).toMatch(/not today/i);
  });

  it("detects scratches, starter changes, and newly posted lineup games from two batter snapshots", async () => {
    const prevPath = path.join(tmpDir, "batters_prev.json");
    const currPath = path.join(tmpDir, "batters_curr.json");
    writeJson(prevPath, {
      hitters: [
        { player_id: "h1", name: "Leadoff Hitter", game_id: "g1", batting_order: 1 },
        { player_id: "h2", name: "Scratched Hitter", game_id: "g1", batting_order: 2 },
      ],
    });
    writeJson(currPath, {
      hitters: [
        { player_id: "h1", name: "Leadoff Hitter", game_id: "g1", batting_order: 2 },
        { player_id: "h3", name: "New Starter", game_id: "g2", batting_order: 1 },
      ],
    });

    const { buildChangeReport } = await import("../changeReport");
    const previous = stubRun({ runId: "run-1", slateDate: "2026-08-12", status: "completed", battersPath: prevPath });
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed", battersPath: currPath });
    const report = buildChangeReport(previous, current);

    expect(report.previousRunId).toBe("run-1");
    expect(report.scratches).toEqual(["Scratched Hitter"]);
    expect(report.starterChanges).toEqual(["Leadoff Hitter: batting order 1 -> 2"]);
    expect(report.newPostedLineupGames).toBe(1); // g2 is new, g1 was already posted
  });

  it("counts salary and projection changes from two player pools", async () => {
    const prevPath = path.join(tmpDir, "pool_prev.json");
    const currPath = path.join(tmpDir, "pool_curr.json");
    writeJson(prevPath, {
      players: [
        { dk_player_id: "d1", mlb_player_id: "h1", salary: 4000, projection: 9 },
        { dk_player_id: "d2", mlb_player_id: "h2", salary: 5000, projection: 8 },
      ],
    });
    writeJson(currPath, {
      players: [
        { dk_player_id: "d1", mlb_player_id: "h1", salary: 4200, projection: 9 },
        { dk_player_id: "d2", mlb_player_id: "h2", salary: 5000, projection: 10 },
      ],
    });

    const { buildChangeReport } = await import("../changeReport");
    const previous = stubRun({ runId: "run-1", slateDate: "2026-08-12", status: "completed", poolPath: prevPath });
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed", poolPath: currPath });
    const report = buildChangeReport(previous, current);

    expect(report.salaryChangedCount).toBe(1);
    expect(report.projectionChangedCount).toBe(1);
  });

  it("counts ownership changes of at least one point from two ownership snapshots", async () => {
    const prevPath = path.join(tmpDir, "ownership_prev.json");
    const currPath = path.join(tmpDir, "ownership_curr.json");
    writeJson(prevPath, { players: [{ dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 20 }] });
    writeJson(currPath, { players: [{ dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 25 }] });

    const { buildChangeReport } = await import("../changeReport");
    const previous = stubRun({ runId: "run-1", slateDate: "2026-08-12", status: "completed", ownershipPath: prevPath });
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed", ownershipPath: currPath });
    const report = buildChangeReport(previous, current);

    expect(report.ownershipChangedCount).toBe(1);
  });

  it("reports exposure changes from two Projection-portfolio lineup sets", async () => {
    const prevPath = path.join(tmpDir, "lineups_prev.json");
    const currPath = path.join(tmpDir, "lineups_curr.json");
    writeJson(prevPath, {
      lineups: [
        { assignments: [{ name: "Player A" }, { name: "Player B" }] },
        { assignments: [{ name: "Player A" }, { name: "Player C" }] },
      ],
    });
    writeJson(currPath, {
      lineups: [
        { assignments: [{ name: "Player A" }, { name: "Player B" }] },
        { assignments: [{ name: "Player A" }, { name: "Player B" }] },
      ],
    });

    const { buildChangeReport } = await import("../changeReport");
    const previous = stubRun({ runId: "run-1", slateDate: "2026-08-12", status: "completed", projectionLineupsPath: prevPath });
    const current = stubRun({ runId: "run-2", slateDate: "2026-08-12", status: "completed", projectionLineupsPath: currPath });
    const report = buildChangeReport(previous, current);

    const byName = Object.fromEntries(report.exposureChanges.map((c) => [c.name, c]));
    expect(byName["Player B"]).toEqual({ name: "Player B", beforePercent: 50, afterPercent: 100 });
    expect(byName["Player C"]).toEqual({ name: "Player C", beforePercent: 50, afterPercent: null });
    expect(byName["Player A"]).toBeUndefined(); // unchanged (100% both times)
  });
});
