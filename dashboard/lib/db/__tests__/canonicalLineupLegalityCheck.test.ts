import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests } from "../executor";
import { checkCanonicalLineupLegality } from "../canonicalLineupLegalityCheck";

function insertSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         schema_version, validation_state, source_provenance, salary_cap, created_at, updated_at
       ) VALUES ('s1', 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-1', 'Main', '2026-08-31', '2026-08-31T23:05:00Z', 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 50000, 'x', 'x')`,
    )
    .run();
}

function insertEligiblePlayer(providerPlayerId: string, positions: string, salary: number, optimizerEligible = 1) {
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, optimizer_eligible, eligibility_status, created_at, updated_at)
       VALUES ('s1', ?, ?, 'BOS', 'TOR', ?, ?, 'UNRESOLVED', ?, 'STARTING_HITTER', 'x', 'x')`,
    )
    .run(providerPlayerId, `Player ${providerPlayerId}`, salary, positions, optimizerEligible);
}

function seedRedundantEligiblePool() {
  for (let i = 0; i < 4; i++) insertEligiblePlayer(`p${i}`, '["P"]', 3000 + i * 100);
  for (const [slot, prefix] of [["C", "c"], ["1B", "1b"], ["2B", "2b"], ["3B", "3b"], ["SS", "ss"]] as const) {
    for (let i = 0; i < 3; i++) insertEligiblePlayer(`${prefix}${i}`, JSON.stringify([slot]), 2000 + i * 100);
  }
  for (let i = 0; i < 6; i++) insertEligiblePlayer(`of${i}`, '["OF"]', 2000 + i * 100);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("M6L: checkCanonicalLineupLegality", () => {
  it("reports SLATE_NOT_FOUND honestly", async () => {
    const result = await checkCanonicalLineupLegality("nope");
    expect(result.status).toBe("SLATE_NOT_FOUND");
  });

  it("only sends optimizer_eligible=1 players to the structural check -- pending/ineligible players never included", async () => {
    insertSlate();
    seedRedundantEligiblePool();
    insertEligiblePlayer("bench-1", '["OF"]', 100, 0); // NOT eligible -- must never appear

    let capturedPlayerIds: string[] = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (_script, args) => {
      const fs = await import("node:fs");
      const inputPath = args[args.indexOf("--input") + 1];
      const payload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
      capturedPlayerIds = payload.players.map((p: { providerPlayerId: string }) => p.providerPlayerId);
      return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","lineupsRequested":1,"lineupsProduced":1,"lineups":[[]]}', stderr: "", command: [] };
    });

    await checkCanonicalLineupLegality("s1");
    expect(capturedPlayerIds).not.toContain("bench-1");
    expect(capturedPlayerIds.length).toBeGreaterThan(0);
  });

  it("real end-to-end: produces a real legal lineup from real eligible canonical players, honoring locks/excludes", async () => {
    insertSlate();
    seedRedundantEligiblePool();

    const result = await checkCanonicalLineupLegality("s1", { count: 2, locks: ["p0"], excludes: ["c0"] });
    expect(result.status).toBe("OK");
    expect(result.lineupsProduced).toBeGreaterThan(0);
    for (const lineup of result.lineups) {
      expect(lineup).toHaveLength(10);
      const ids = lineup.map((p) => p.providerPlayerId);
      expect(ids).toContain("p0");
      expect(ids).not.toContain("c0");
      expect(lineup.reduce((sum, p) => sum + p.salary, 0)).toBeLessThanOrEqual(50000);
    }
  });

  it("cleans up its temp input file after a run", async () => {
    insertSlate();
    seedRedundantEligiblePool();
    let capturedDir: string | null = null;
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    const realFs = await import("node:fs");
    __setPythonRunnerForTests(async (_script, args) => {
      const inputPath = args[args.indexOf("--input") + 1];
      capturedDir = inputPath.replace(/[\\/]players\.json$/, "");
      expect(realFs.existsSync(inputPath)).toBe(true);
      return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","lineupsRequested":1,"lineupsProduced":0,"lineups":[]}', stderr: "", command: [] };
    });

    await checkCanonicalLineupLegality("s1");
    expect(realFs.existsSync(capturedDir!)).toBe(false);
  });
});
