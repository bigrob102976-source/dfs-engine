import fs from "node:fs";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests } from "../executor";
import { computeAndPersistEligibilityForSlate } from "../canonicalEligibility";

function insertSlate(overrides: Partial<{ internal_slate_id: string; slate_date: string }> = {}) {
  const row = { internal_slate_id: "s1", slate_date: "2026-08-31", ...overrides };
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         schema_version, validation_state, source_provenance, created_at, updated_at
       ) VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-1', 'Main', ?, '2026-08-31T23:05:00Z', 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.slate_date);
  return row;
}

function insertPlayer(overrides: Partial<{ provider_player_id: string; internal_player_id: string | null; identity_status: string }> = {}) {
  const row = { provider_player_id: "1", internal_player_id: null, identity_status: "UNRESOLVED", ...overrides };
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, internal_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES ('s1', ?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', ?, 'x', 'x')`,
    )
    .run(row.provider_player_id, row.internal_player_id, row.identity_status);
  return row;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

async function setFakeRunner(resultJson: object) {
  const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __setPythonRunnerForTests(async () => ({ exitCode: 0, stdout: `RESULT_JSON:${JSON.stringify(resultJson)}`, stderr: "", command: [] }));
}

describe("M6D: computeAndPersistEligibilityForSlate", () => {
  it("reports SLATE_NOT_FOUND honestly for an unknown internalSlateId", async () => {
    const result = await computeAndPersistEligibilityForSlate("no-such-slate");
    expect(result.status).toBe("SLATE_NOT_FOUND");
  });

  it("persists real eligibility results onto the SAME slate_players rows -- no duplicate row, salary/identity untouched", async () => {
    insertSlate();
    insertPlayer({ provider_player_id: "1" });
    await setFakeRunner({
      status: "OK", date: "2026-08-31",
      results: [{ providerPlayerId: "1", gameId: "g1", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, battingOrder: 4 }],
    });

    const result = await computeAndPersistEligibilityForSlate("s1");
    expect(result.status).toBe("OK");
    expect(result.playersUpdated).toBe(1);

    const row = getDb().prepare("SELECT * FROM slate_players WHERE internal_slate_id='s1' AND provider_player_id='1'").get() as Record<string, unknown>;
    expect(row.game_id).toBe("g1");
    expect(row.eligibility_status).toBe("STARTING_HITTER");
    expect(row.optimizer_eligible).toBe(1);
    expect(row.batting_order).toBe(4);
    expect(row.eligibility_computed_at).toBeTruthy();
    // Identity/salary rows untouched by this update.
    expect(row.salary).toBe(4500);
    expect(row.team).toBe("BOS");

    const count = (getDb().prepare("SELECT COUNT(*) as c FROM slate_players WHERE internal_slate_id='s1'").get() as { c: number }).c;
    expect(count).toBe(1); // never duplicated
  });

  it("reports NO_RESEARCH_PACKAGE honestly, never crashes, never fabricates results", async () => {
    insertSlate();
    insertPlayer();
    await setFakeRunner({ status: "NO_RESEARCH_PACKAGE", date: "2026-08-31", reason: "no package yet", results: [] });

    const result = await computeAndPersistEligibilityForSlate("s1");
    expect(result.status).toBe("NO_RESEARCH_PACKAGE");
    expect(result.playersUpdated).toBe(0);

    const row = getDb().prepare("SELECT eligibility_status FROM slate_players WHERE internal_slate_id='s1'").get() as { eligibility_status: string | null };
    expect(row.eligibility_status).toBeNull(); // still honestly un-computed
  });

  it("cleans up its temp input file after a run", async () => {
    insertSlate();
    insertPlayer();
    let capturedDir: string | null = null;
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (_script, args) => {
      const inputPath = args[args.indexOf("--input") + 1];
      capturedDir = inputPath.replace(/[\\/]players\.json$/, "");
      expect(fs.existsSync(inputPath)).toBe(true); // real file, real payload, at call time
      return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-08-31","results":[]}', stderr: "", command: [] };
    });

    await computeAndPersistEligibilityForSlate("s1");
    expect(capturedDir).toBeTruthy();
    expect(fs.existsSync(capturedDir!)).toBe(false); // cleaned up in finally
  });

  it("resolves mlbPlayerId for RESOLVED players and passes null for UNRESOLVED ones in the payload sent to Python", async () => {
    insertSlate();
    getDb().prepare("INSERT INTO players (internal_player_id, sport, canonical_name, normalized_name, active, created_at, updated_at) VALUES ('ip-1', 'MLB', 'A', 'a', 1, 'x', 'x')").run();
    getDb()
      .prepare(
        `INSERT INTO player_external_ids (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, is_current, valid_from, created_at, updated_at)
         VALUES ('e1', 'ip-1', 'MLB', 'mlbam', '660271', 'mlbam_id', 'exact_deterministic_source_mapping', 1.0, 1, 'x', 'x', 'x')`,
      )
      .run();
    insertPlayer({ provider_player_id: "1", internal_player_id: "ip-1", identity_status: "RESOLVED" });
    insertPlayer({ provider_player_id: "2", internal_player_id: null, identity_status: "UNRESOLVED" });

    let capturedPayload: { players: Array<{ providerPlayerId: string; mlbPlayerId: string | null }> } | null = null;
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (_script, args) => {
      const inputPath = args[args.indexOf("--input") + 1];
      capturedPayload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
      return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-08-31","results":[]}', stderr: "", command: [] };
    });

    await computeAndPersistEligibilityForSlate("s1");
    const byId = new Map(capturedPayload!.players.map((p) => [p.providerPlayerId, p.mlbPlayerId]));
    expect(byId.get("1")).toBe("660271");
    expect(byId.get("2")).toBeNull();
  });
});
