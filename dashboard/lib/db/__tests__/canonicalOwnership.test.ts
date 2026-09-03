import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests } from "../executor";
import { __resetStorageForTests } from "../../storage/getStorage";
import { computeAndPersistOwnershipForSlate, getCanonicalOwnershipForSlate } from "../canonicalOwnership";
import type { OptimizerPoolResult, PoolPlayerRow } from "../../optimizerWorkspace/types";

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function insertSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         schema_version, validation_state, source_provenance, created_at, updated_at
       ) VALUES ('s1', 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-1', 'Main', '2026-08-31', '2026-08-31T23:05:00Z', 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run();
}

function player(overrides: Partial<PoolPlayerRow>): PoolPlayerRow {
  return {
    dkPlayerId: "1", mlbPlayerId: "660271", name: "Player", team: "BOS", opponent: "TOR", gameId: "g1",
    playerType: "hitter", positions: ["OF"], battingOrder: 1, salary: 4500,
    projection: 10, ceiling: 16, value: 2.2, ownership: null, leverage: null, risk: null, confidence: null,
    lineupStatus: "STARTING_HITTER", matchStatus: "matched", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true,
    externalProjection: null, adjustedProjection: null, adjustmentDelta: null, adjustmentPercent: null, adjustmentReasons: [],
    aiProjection: null, aiCeiling: null, aiFloor: null, aiDelta: null, aiConfidence: null, aiRisk: null, aiGrade: null,
    aiValueScore: null, aiSignals: [], aiReasons: [], aiSummary: null,
    nativeProjection: 10, nativeCeiling: 16, nativeFloor: 3, nativeDelta: 0, nativeConfidence: null, nativeReasons: [],
    nativeExpectedPa: null, nativeExpectedInnings: null, nativeHitterComponents: null, nativePitcherComponents: null,
    fantasyProsProjection: null, fantasyProsMatchStatus: null,
    mlProjection: null, mlDataQualityScore: null, mlProjectionStatus: null, mlFeatureTimestamp: null,
    blueCollarProjection: null, blueCollarRawProjection: null, blueCollarMatchStatus: null,
    ...overrides,
  };
}

function pool(players: PoolPlayerRow[]): OptimizerPoolResult {
  return {
    date: "2026-08-31", slateId: "dkunofficial-1", slateName: "Main", providerName: "draftkings_unofficial",
    isMock: false, providerSource: "draftkings_unofficial_live", generatedAt: "2026-08-31T18:00:00.000Z",
    players, activePlayers: players.filter((p) => p.optimizerEligible).length, pitcherCount: 0, hitterCount: players.length,
    confirmedLineupGames: 1, unconfirmedLineupGames: 0, unmatchedCount: 0, slateGames: 1, rosterFeasibilityPass: true,
    salaryCap: 50000, hasOwnership: false, hasExternalProjections: false, externalProviderName: null,
    hasAiProjections: false, hasNativeProjections: true, hasFantasyProsProjections: false, hasMlProjections: false,
    hasBlueCollarProjections: false, blueCollarSlateName: null, blueCollarSlateMatchStatus: null, blueCollarUpdated: null,
    blueCollarCoverage: { total: 0, matched: 0, unmatched: 0, ambiguous: 0 } as never,
    vegasCoverage: { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, games: [] } as never,
    dataStatus: "fresh", artifactAgeSeconds: 0, lastUpdatedAt: "2026-08-31T18:00:00.000Z", eligibilityComputedAt: "2026-08-31T18:00:00.000Z",
  };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-canonical-ownership-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("MLB FINISH MODE Phase D: computeAndPersistOwnershipForSlate", () => {
  it("reports SLATE_NOT_FOUND honestly for an unknown internalSlateId", async () => {
    const result = await computeAndPersistOwnershipForSlate("no-such-slate", pool([]));
    expect(result.status).toBe("SLATE_NOT_FOUND");
  });

  it("reports NO_USABLE_PLAYERS honestly (never fake 0%) when no optimizer-eligible player has both a projection and ceiling", async () => {
    insertSlate();
    const result = await computeAndPersistOwnershipForSlate("s1", pool([player({ projection: null, ceiling: null })]));
    expect(result.status).toBe("NO_USABLE_PLAYERS");
    expect(result.playersUpdated).toBe(0);
  });

  it("runs the real ownership script against a materialized pool file and persists its real output", async () => {
    insertSlate();
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script, args) => {
      expect(script).toBe("scripts/project_dk_ownership.py");
      expect(args).toContain("--pool");
      const poolPath = args[args.indexOf("--pool") + 1];
      expect(fs.existsSync(poolPath)).toBe(true); // real materialized file, real payload, at call time
      const poolDoc = JSON.parse(fs.readFileSync(poolPath, "utf-8"));
      expect(poolDoc.players[0].projection).toBe(10); // real projection flowed into the materialized pool

      writeJson("ownership_predictions/2026-08-31/dkunofficial-1/ownership_20260831T180500000000.json", {
        slate_date: "2026-08-31", slate_id: "dkunofficial-1", generated_at: "2026-08-31T18:05:00.000Z", model_version: "0.1.0",
        player_count: 1,
        players: [{ dk_player_id: "1", mlb_player_id: "660271", name: "Player", team: "BOS", projected_ownership: 24.5, ownership_tier: "chalk", leverage_score: -2.1, chalk_score: 80 }],
        team_popularity: {}, normalization_checks: {},
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    const result = await computeAndPersistOwnershipForSlate("s1", pool([player({})]));
    expect(result.status).toBe("OK");
    expect(result.playersUpdated).toBe(1);

    const rows = await getCanonicalOwnershipForSlate("s1");
    expect(rows.get("1")).toEqual(
      expect.objectContaining({ projected_ownership: 24.5, ownership_tier: "chalk", leverage_score: -2.1, chalk_score: 80, model_version: "0.1.0" }),
    );
  });

  it("reports ERROR honestly (never fake data) when the real script fails", async () => {
    insertSlate();
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({ exitCode: 1, stdout: "", stderr: "ownership model crashed", command: [] }));

    const result = await computeAndPersistOwnershipForSlate("s1", pool([player({})]));
    expect(result.status).toBe("ERROR");
    expect(result.reason).toContain("ownership model crashed");
    const rows = await getCanonicalOwnershipForSlate("s1");
    expect(rows.size).toBe(0); // never a fabricated fallback row
  });

  it("cleans up the materialized temp pool file after a run", async () => {
    insertSlate();
    let capturedDir: string | null = null;
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (_script, args) => {
      const poolPath = args[args.indexOf("--pool") + 1];
      capturedDir = path.dirname(poolPath);
      writeJson("ownership_predictions/2026-08-31/dkunofficial-1/ownership_20260831T180500000000.json", {
        slate_date: "2026-08-31", slate_id: "dkunofficial-1", generated_at: "x", model_version: "0.1.0", player_count: 0,
        players: [], team_popularity: {}, normalization_checks: {},
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    await computeAndPersistOwnershipForSlate("s1", pool([player({})]));
    expect(capturedDir).toBeTruthy();
    expect(fs.existsSync(capturedDir!)).toBe(false);
  });
});
