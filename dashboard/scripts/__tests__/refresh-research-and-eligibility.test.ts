import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../lib/db/client";
import { __resetExecutorForTests } from "../../lib/db/executor";
import { __resetStorageForTests } from "../../lib/storage/getStorage";
import { parseArgs, runRefresh } from "../refresh-research-and-eligibility";

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function insertCanonicalSlate(internalSlateId: string, providerSlateId: string, slateDate = "2026-09-02") {
  getDb()
    .prepare(
      `INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, source_provenance, created_at, updated_at)
       VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, ?, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(internalSlateId, providerSlateId, slateDate, `${slateDate}T23:05:00Z`);
}

function insertCanonicalPlayer(internalSlateId: string, providerPlayerId: string) {
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES (?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', 'UNRESOLVED', 'x', 'x')`,
    )
    .run(internalSlateId, providerPlayerId);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-refresh-orchestration-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("T3: refresh-research-and-eligibility.ts parseArgs", () => {
  it("parses --date and defaults --sport to MLB", () => {
    expect(parseArgs(["--date", "2026-09-02"])).toEqual({ date: "2026-09-02", sport: "MLB" });
  });

  it("accepts an explicit --sport", () => {
    expect(parseArgs(["--date", "2026-09-02", "--sport", "NFL"])).toEqual({ date: "2026-09-02", sport: "NFL" });
  });

  it("throws with a clear usage message when --date is missing", () => {
    expect(() => parseArgs([])).toThrow(/Usage/);
  });
});

describe("T3: runRefresh -- the automatic research/identity/eligibility orchestration", () => {
  it("runs all three real steps and reports OK for each on a healthy day", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(true);
    expect(summary.identity.ok).toBe(true);
    expect(summary.eligibility.ok).toBe(true);
    expect(summary.eligibility.slatesFound).toBe(1);
    expect(summary.eligibility.slatesUpdated).toBe(1);
  });

  it("T3 Step 5/11: a research package failure never prevents identity refresh or eligibility recompute from running", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 1, stdout: "", stderr: "MLB Stats API unreachable", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(false);
    expect(summary.research.detail).toContain("MLB Stats API unreachable");
    // The other two steps still ran and succeeded -- one failure does not cascade.
    expect(summary.identity.ok).toBe(true);
    expect(summary.eligibility.ok).toBe(true);
  });

  it("T3 Step 5/11: an identity refresh failure never prevents research refresh or eligibility recompute from running", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 1, stdout: "", stderr: "roster fetch failed", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(true);
    expect(summary.identity.ok).toBe(false);
    expect(summary.identity.detail).toContain("roster fetch failed");
    expect(summary.eligibility.ok).toBe(true);
  });

  it("T3 Step 5/11: an eligibility recompute failure for one slate never destroys a sibling slate's good state, and never stops the whole run", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    insertCanonicalSlate("s2", "dkunofficial-2");
    insertCanonicalPlayer("s2", "2");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    let callIndex = 0;
    __setPythonRunnerForTests(async (script, args) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        callIndex += 1;
        // Fail the first slate's eligibility compute, succeed the second --
        // proves per-slate isolation from inside this orchestration script,
        // not just inside refreshCanonicalEligibilityForDate in isolation.
        const inputPath = args[args.indexOf("--input") + 1];
        const fs = await import("node:fs");
        const payload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
        if (payload.date === "2026-09-02" && callIndex === 1) {
          return { exitCode: 1, stdout: "", stderr: "crash", command: [] };
        }
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.eligibility.slatesFound).toBe(2);
    expect(summary.eligibility.slatesFailed).toBe(1);
    expect(summary.eligibility.slatesUpdated).toBe(1);
    expect(summary.eligibility.ok).toBe(false); // honestly degraded, never hidden
  });

  it("never throws even when every step fails -- always returns a summary", async () => {
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({ exitCode: 1, stdout: "", stderr: "total outage", command: [] }));

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(false);
    expect(summary.identity.ok).toBe(false);
    // Zero canonical slates exist for this date in this test's DB -- an
    // honest "nothing to do" success, never fabricated.
    expect(summary.eligibility.slatesFound).toBe(0);
  });
});

function insertResolvedPlayerIdentity(internalPlayerId: string, mlbExternalId: string) {
  getDb()
    .prepare("INSERT INTO players (internal_player_id, sport, canonical_name, normalized_name, active, created_at, updated_at) VALUES (?, 'MLB', 'A', 'a', 1, 'x', 'x')")
    .run(internalPlayerId);
  getDb()
    .prepare(
      `INSERT INTO player_external_ids (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, is_current, valid_from, created_at, updated_at)
       VALUES (?, ?, 'MLB', 'mlbam', ?, 'mlbam_id', 'exact_deterministic_source_mapping', 1.0, 1, 'x', 'x', 'x')`,
    )
    .run(`ext-${internalPlayerId}`, internalPlayerId, mlbExternalId);
}

function writeNativeSnapshot(date: string) {
  writeJson(`native_projection_snapshots/${date}/native_projection_20260902T180000000000.json`, {
    slate_date: date, generated_at: "2026-09-02T18:00:00.000Z", model_version: "1.0.0",
    pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
    player_count: 1,
    players: [{
      player_id: "660271", name: "Player", team: "BOS", player_type: "hitter", opponent: "TOR", game_id: "g1", salary: 4500,
      positions: ["OF"], batting_order: 3, native_projection: 11.5, native_ceiling: 18.0, native_floor: 4.0,
      confidence: 80, variance: 2, model_version: "1.0.0",
      hitter_opportunity: null, pitcher_opportunity: null, hitter_components: null, pitcher_components: null,
      input_coverage: null, reasons: [], warnings: [], generated_at: "2026-09-02T18:00:00.000Z",
      source_pitcher_snapshot_path: null, source_batter_snapshot_path: null, source_environment_snapshot_path: null,
    }],
    warnings: [],
  });
}

describe("MLB FINISH MODE Phase B/D/I: Native projection + ownership orchestration", () => {
  it("MLB FINISH MODE Phase C: a pitcher/batter agent failure is isolated -- never prevents eligibility/other steps from succeeding, and the OTHER agent still runs", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/run_real_pitcher_agent.py") return { exitCode: 1, stdout: "", stderr: "pitcher agent crashed", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.pitcherAgent.ok).toBe(false);
    expect(summary.pitcherAgent.detail).toContain("pitcher agent crashed");
    expect(summary.batterAgent.ok).toBe(true); // the OTHER agent is unaffected
    expect(summary.eligibility.ok).toBe(true);
  });

  it("a Native engine failure is isolated -- never prevents eligibility/other steps from succeeding", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/run_native_projection_engine.py") return { exitCode: 1, stdout: "", stderr: "native engine crashed", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.nativeProjectionEngine.ok).toBe(false);
    expect(summary.nativeProjectionEngine.detail).toContain("native engine crashed");
    expect(summary.eligibility.ok).toBe(true); // unaffected
    expect(summary.identity.ok).toBe(true); // unaffected
  });

  it("real end-to-end: research succeeds -> eligibility computes -> Native snapshot generated -> projections persist -> ownership runs and persists -- all in ONE pass, no manual intervention", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1", "2026-09-02");
    insertResolvedPlayerIdentity("ip-1", "660271");
    getDb()
      .prepare(
        `INSERT INTO slate_players (internal_slate_id, provider_player_id, internal_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
         VALUES ('s1', '1', 'ip-1', 'Player', 'BOS', 'TOR', 4500, '["OF"]', 'RESOLVED', 'x', 'x')`,
      )
      .run();

    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script, args) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return {
          exitCode: 0,
          stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[{"providerPlayerId":"1","gameId":"g1","eligibilityStatus":"STARTING_HITTER","optimizerEligible":true,"battingOrder":3}]}',
          stderr: "", command: [],
        };
      }
      if (script === "scripts/run_native_projection_engine.py") {
        writeNativeSnapshot("2026-09-02");
        return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      }
      if (script === "scripts/project_dk_ownership.py") {
        const poolPath = args[args.indexOf("--pool") + 1];
        const poolDoc = JSON.parse(fs.readFileSync(poolPath, "utf-8"));
        expect(poolDoc.players[0].projection).toBe(11.5); // real projection flowed all the way into ownership's own input
        writeJson("ownership_predictions/2026-09-02/dkunofficial-1/ownership_20260902T181000000000.json", {
          slate_date: "2026-09-02", slate_id: "dkunofficial-1", generated_at: "2026-09-02T18:10:00.000Z", model_version: "0.1.0",
          player_count: 1,
          players: [{ dk_player_id: "1", mlb_player_id: "660271", name: "Player", team: "BOS", projected_ownership: 30.2, ownership_tier: "chalk", leverage_score: -1.0, chalk_score: 75 }],
          team_popularity: {}, normalization_checks: {},
        });
        return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(true);
    expect(summary.eligibility.ok).toBe(true);
    expect(summary.nativeProjectionEngine.ok).toBe(true);
    expect(summary.projections.ok).toBe(true);
    expect(summary.projections.slatesUpdated).toBe(1);
    expect(summary.ownership.ok).toBe(true);
    expect(summary.ownership.slatesUpdated).toBe(1);

    // Real, persisted end state -- no manual /api/admin/* call was ever made.
    const projRow = getDb().prepare("SELECT projection, ceiling FROM canonical_slate_player_projections WHERE internal_slate_id='s1'").get() as Record<string, unknown>;
    expect(projRow.projection).toBe(11.5);
    const ownRow = getDb().prepare("SELECT projected_ownership FROM canonical_slate_player_ownership WHERE internal_slate_id='s1'").get() as Record<string, unknown>;
    expect(ownRow.projected_ownership).toBe(30.2);
  });

  it("MLB FINISH MODE Phase I: ownership is honestly SKIPPED (not re-run) when a recent generation already exists -- debounced, not hammered every cycle", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1", "2026-09-02");
    getDb()
      .prepare(
        `INSERT INTO canonical_slate_player_ownership (id, internal_slate_id, provider_player_id, model_version, projected_ownership, ownership_tier, leverage_score, chalk_score, generated_at, created_at, updated_at)
         VALUES ('o1', 's1', '1', '0.1.0', 20, 'balanced', 0, 50, ?, 'x', 'x')`,
      )
      .run(new Date().toISOString()); // just generated

    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/project_dk_ownership.py") throw new Error("ownership script must NOT be invoked when a recent generation already exists");
      return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.ownership.skipped).toBe(true);
    expect(summary.ownership.ok).toBe(true);
  });
});
