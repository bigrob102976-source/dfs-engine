import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { __resetStorageForTests } from "../../storage/getStorage";
import { compareAllServingBackendsForDate, compareServingBackends } from "../comparison";

const DATE = "2026-08-31";
let tmpDir: string;
let tsCounter = 0;

function nextTs(): string {
  tsCounter += 1;
  return String(tsCounter).padStart(10, "0");
}

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

/** loadPool() (the legacy backend) ALWAYS invokes
 * scripts/build_dfs_pool_from_provider.py to build the actual player
 * pool, even when reusing an already-fresh provider-slate document --
 * only the DISCOVERY/FETCH step is skippable. Fakes that one subprocess
 * call by writing the dk_player_pool_*.json/dk_match_report_*.json
 * artifacts directly, mirroring poolCache.test.ts's own convention. */
function fakePythonRunnerFor(players: Array<{ dkPlayerId: string; name: string; team: string; salary: number; positions: string[] }>) {
  return async (script: string) => {
    if (script === "scripts/build_dfs_pool_from_provider.py") {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        roster_feasibility_pass: true,
        player_count: players.length,
        players: players.map((p) => ({
          dk_player_id: p.dkPlayerId, mlb_player_id: null, name: p.name, team: p.team, player_type: "hitter",
          dk_positions: p.positions, salary: p.salary, projection: null, ceiling: null, risk_score: null, confidence: null,
          batting_order: null, game_id: null, opponent: "TOR", lineup_status: "active", match_status: "unmatched",
          eligibility_status: null, optimizer_eligible: false,
        })),
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        dk_entries: players.length, matched_to_mlb: 0, unmatched_count: players.length, dk_games_total: 8,
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/project_dk_ownership.py") {
      return { exitCode: 1, stdout: "", stderr: "no ownership in this test", command: [] };
    }
    throw new Error(`Unexpected script invocation in this test: ${script}`);
  };
}

function seedLegacyArtifact(overrides: { salary?: number; team?: string; positions?: string[]; extraPlayer?: boolean } = {}) {
  writeJson(`dfs_input/${DATE}/provider_slate_0000000001.json`, {
    status: "ready", provider_name: "draftkings_unofficial", is_mock: false, source: "draftkings_unofficial_live",
    generated_at_utc: new Date().toISOString(), selected_slate_id: "dkunofficial-152904",
    slates: [{ slate_id: "dkunofficial-152904", slate_name: "Main", game_count: 8, start_time: null }],
    players: [
      {
        external_player_id: "1", name: "Flex Player", team: overrides.team ?? "BOS", opponent: "TOR", game: "TOR@BOS",
        salary: overrides.salary ?? 4500, position_eligibility: overrides.positions ?? ["OF"], slate_id: "dkunofficial-152904",
        slate_name: "Main", start_time: null, source: "draftkings_unofficial", retrieved_at: new Date().toISOString(),
      },
      ...(overrides.extraPlayer
        ? [{
            external_player_id: "2", name: "Legacy Only Player", team: "TOR", opponent: "BOS", game: "TOR@BOS",
            salary: 4000, position_eligibility: ["1B"], slate_id: "dkunofficial-152904", slate_name: "Main",
            start_time: null, source: "draftkings_unofficial", retrieved_at: new Date().toISOString(),
          }]
        : []),
    ],
  });
}

function seedCanonicalSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, schema_version, validation_state, source_provenance, promoted_at,
         player_count, created_at, updated_at
       ) VALUES ('s1', 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-152904', 'Main', ?, '2026-08-31T23:05:00Z', 8, '[]', 50000, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', ?, 1, 'x', 'x')`,
    )
    .run(DATE, new Date().toISOString());
}

function seedCanonicalPlayer(overrides: { salary?: number; team?: string; positions?: string } = {}) {
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, game_id, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES ('s1', '1', 'Flex Player', ?, 'TOR', NULL, ?, ?, 'UNRESOLVED', 'x', 'x')`,
    )
    .run(overrides.team ?? "BOS", overrides.salary ?? 4500, overrides.positions ?? JSON.stringify(["OF"]));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-comparison-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../../optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

const ONE_PLAYER = [{ dkPlayerId: "1", name: "Flex Player", team: "BOS", salary: 4500, positions: ["OF"] }];
const TWO_PLAYERS = [...ONE_PLAYER, { dkPlayerId: "2", name: "Legacy Only Player", team: "TOR", salary: 4000, positions: ["1B"] }];

async function setFakeRunner(players: typeof ONE_PLAYER) {
  const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __setPythonRunnerForTests(fakePythonRunnerFor(players));
}

describe("M5D: compareServingBackends", () => {
  it("reports MATCH when core fields agree", async () => {
    seedLegacyArtifact();
    await setFakeRunner(ONE_PLAYER);
    seedCanonicalSlate();
    seedCanonicalPlayer();

    const result = await compareServingBackends(DATE, "dkunofficial-152904");
    expect(result.legacyFound).toBe(true);
    expect(result.canonicalFound).toBe(true);
    expect(result.match).toBe(true);
    expect(result.differences.salaryMismatches).toEqual([]);
  });

  it("reports a real salary DIFFERENCE with a structured, safe count -- never exposes secrets", async () => {
    seedLegacyArtifact({ salary: 5000 });
    await setFakeRunner([{ ...ONE_PLAYER[0], salary: 5000 }]);
    seedCanonicalSlate();
    seedCanonicalPlayer({ salary: 4500 });

    const result = await compareServingBackends(DATE, "dkunofficial-152904");
    expect(result.match).toBe(false);
    expect(result.differences.salaryMismatches).toHaveLength(1);
    expect(result.differences.salaryMismatches[0]).toEqual(
      expect.objectContaining({ dkPlayerId: "1", legacySalary: 5000, canonicalSalary: 4500 }),
    );
    const serialized = JSON.stringify(result);
    for (const forbidden of ["DATABASE_URL", "postgres://", "AWS_SECRET", "STRIPE_SECRET"]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("reports missingInCanonical when legacy has a player canonical never promoted", async () => {
    seedLegacyArtifact({ extraPlayer: true });
    await setFakeRunner(TWO_PLAYERS);
    seedCanonicalSlate();
    seedCanonicalPlayer();

    const result = await compareServingBackends(DATE, "dkunofficial-152904");
    expect(result.match).toBe(false);
    expect(result.differences.missingInCanonical).toEqual(["2"]);
    expect(result.differences.missingInLegacy).toEqual([]);
  });

  it("reports canonicalFound=false honestly when canonical has never promoted this slate", async () => {
    seedLegacyArtifact();
    await setFakeRunner(ONE_PLAYER);
    const result = await compareServingBackends(DATE, "dkunofficial-152904");
    expect(result.legacyFound).toBe(true);
    expect(result.canonicalFound).toBe(false);
    expect(result.match).toBe(false);
    expect(result.canonicalError).toBeTruthy();
  });
});

describe("M5E: compareAllServingBackendsForDate", () => {
  it("compares every legacy-listed slate and produces an aggregate report", async () => {
    seedLegacyArtifact();
    await setFakeRunner(ONE_PLAYER);
    seedCanonicalSlate();
    seedCanonicalPlayer();

    const report = await compareAllServingBackendsForDate(DATE);
    expect(report.slatesCompared).toBe(1);
    expect(report.exactMatches).toBe(1);
    expect(report.mismatches).toBe(0);
    expect(report.eligibilityMismatchesNote).toMatch(/CANONICAL_UNCONFIRMED/);
  });
});
