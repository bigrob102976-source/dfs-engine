import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../orchestrator/pythonRunner";

import { __resetStorageForTests } from "../storage/getStorage";

let tmpDir: string;
let tsCounter = 0;
const DATE = "2026-08-19";
const SLATE_ID = "mock-main";

function nextTs(): string {
  tsCounter += 1;
  return String(tsCounter).padStart(10, "0");
}

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function ok(stdout = "ok"): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}
function fail(stderr = "boom"): PythonRunResult {
  return { exitCode: 1, stdout: "", stderr, command: [] };
}

type Handler = (args: string[]) => PythonRunResult | Promise<PythonRunResult>;

function defaultHandlers(): Record<string, Handler> {
  return {
    // M32.7: refreshes research_output/<date>/{games,teams,pitchers,batters}.json
    // from the live MLB schedule/lineups -- always exits 0.
    "scripts/build_research_package.py": () => ok(),
    // M32.7: re-scores confirmed starters through the Pitcher/Batter
    // Agents -- always exits 0 for the normal "nothing new to score yet"
    // case too, not just success.
    "scripts/run_real_pitcher_agent.py": () => ok(),
    "scripts/run_real_batter_agent.py": () => ok(),
    "scripts/fetch_dfs_slate.py": () => {
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "ready", provider_name: "draftkings_csv", is_mock: false, source: "real_dk_csv",
        selected_slate_id: SLATE_ID,
        slates: [{ slate_id: SLATE_ID, slate_name: "Main", game_count: 1, start_time: null }],
        players: [],
      });
      return ok();
    },
    "scripts/build_dfs_pool_from_provider.py": () => {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        selected_slate_id: SLATE_ID, roster_feasibility_pass: true, player_count: 1,
        players: [{
          dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter",
          dk_positions: ["OF"], salary: 4000, projection: 10, ceiling: 18, risk_score: 30, confidence: 80,
          batting_order: 1, game_id: "g1", opponent: "TOR", lineup_status: "active", match_status: "matched",
          source_sha256: "abc123hash",
        }],
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1, dk_games_matched_to_research: 1,
        source_provenance: "OFFICIAL_USER_UPLOAD",
        identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
      });
      return ok();
    },
    "scripts/project_dk_ownership.py": () => {
      writeJson(`ownership_predictions/${DATE}/${SLATE_ID}/ownership_${nextTs()}.json`, {
        slate_id: SLATE_ID, players: [{ dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 22, leverage_score: 5 }],
      });
      return ok();
    },
    // Canonical MLB Player Identity Foundation: refreshes the roster-
    // derived identity crosswalk. Always exits 0 and reports status via
    // a trailing JSON line -- see player_identity/refresh.py.
    "scripts/refresh_player_identity.py": () => ok(JSON.stringify({ status: "ready", teams_total: 0, teams_fetched: 0 })),
    // M32.7: Vegas/weather/park refresh -- always exits 0, JSON status
    // line, same non-blocking contract as identity refresh above.
    "scripts/build_game_environment_report.py": () => ok(JSON.stringify({ status: "ready", game_count: 1 })),
    "scripts/run_native_projection_engine.py": () => {
      writeJson(`native_projection_snapshots/${DATE}/native_projection_${nextTs()}.json`, {
        slate_date: DATE, generated_at: "x", model_version: "1.0.0", player_count: 1,
        players: [{ player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter" }], warnings: [],
      });
      return ok(JSON.stringify({ status: "ready", hitter_count: 1, pitcher_count: 0 }));
    },
    "scripts/run_ai_projection_engine.py": () => {
      writeJson(`ai_projection_snapshots/${DATE}/ai_projection_${nextTs()}.json`, {
        slate_date: DATE, generated_at: "x", model_version: "0.1.0", player_count: 1,
        players: [{ player_id: "h1", name: "Leadoff Hitter" }], warnings: [],
      });
      return ok(JSON.stringify({ status: "ready", player_count: 1 }));
    },
    // FantasyPros: optional, test/evaluation comparison source. The
    // default/expected outcome for a test env with no API key configured
    // is "not_configured" (exit 0, JSON status line) -- never a Python
    // exception -- see fantasypros/build.py::build_fantasypros_snapshot.
    "scripts/fetch_fantasypros_projections.py": () => ok(JSON.stringify({ status: "not_configured" })),
    // BlueCollar DFS: optional, ADMIN-testable comparison/optimizer
    // source. The default/expected outcome for a test env with no API
    // key configured is "not_configured" (exit 0, JSON status line) --
    // never a Python exception -- see bluecollar/build.py::build_bluecollar_snapshot.
    "scripts/fetch_bluecollar_projections.py": () => ok(JSON.stringify({ status: "not_configured" })),
    // Milestone 32.2B: Big Money ML shadow inference -- same non-blocking,
    // always-exit-0-for-expected-outcomes contract as FantasyPros above.
    "scripts/run_ml_shadow_inference.py": () => ok(JSON.stringify({ status: "no_eligible_pitchers" })),
    // Milestone 32.3B: hitter side of the same shadow inference.
    "scripts/run_ml_hitter_shadow_inference.py": () => ok(JSON.stringify({ status: "no_eligible_hitters" })),
  };
}

function makeFakeRunner(handlers: Record<string, Handler>, calls: Array<{ script: string; args: string[] }>): PythonRunner {
  return async (script, args) => {
    calls.push({ script, args });
    const handler = handlers[script];
    if (!handler) throw new Error(`No fake handler registered for script: ${script}`);
    return handler(args);
  };
}

beforeEach(async () => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-slatepipeline-"));
  tsCounter = 0;
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  const { __resetDbForTests } = await import("../db/client");
  const { __resetExecutorForTests } = await import("../db/executor");
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("runSlatePipeline", () => {
  it("marks the slate READY when every required signal is produced", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors).toEqual([]);
    expect(calls.map((c) => c.script)).toEqual([
      "scripts/build_research_package.py",
      "scripts/run_real_pitcher_agent.py",
      "scripts/run_real_batter_agent.py",
      "scripts/fetch_dfs_slate.py",
      "scripts/build_dfs_pool_from_provider.py",
      "scripts/project_dk_ownership.py",
      "scripts/refresh_player_identity.py",
      "scripts/build_game_environment_report.py",
      "scripts/run_native_projection_engine.py",
      "scripts/run_ai_projection_engine.py",
      "scripts/fetch_fantasypros_projections.py",
      "scripts/fetch_bluecollar_projections.py",
      "scripts/run_ml_shadow_inference.py",
      "scripts/run_ml_hitter_shadow_inference.py",
    ]);

    const { getSlateStatus } = await import("../db/slateStatus");
    const status = (await getSlateStatus(DATE, SLATE_ID))!;
    expect(status.status).toBe("READY");
    expect(status.pool_path).toContain("dk_player_pool_");
    expect(status.native_snapshot_path).toContain("native_projection_");
    expect(status.ai_snapshot_path).toContain("ai_projection_");
    expect(status.source_hash).toBe("abc123hash");
    expect(status.source_provenance).toBe("OFFICIAL_USER_UPLOAD");
  });

  it("marks the slate PARTIAL when the pool builds but native projections fail", async () => {
    const handlers = { ...defaultHandlers(), "scripts/run_native_projection_engine.py": () => fail("no board yet") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("PARTIAL");
    expect(result.errors.some((e) => e.includes("Native projection engine failed"))).toBe(true);

    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("PARTIAL");
  });

  it("Milestone 31.1: marks a half-posted-lineup slate PARTIAL (re-pullable), never READY, even when everything else succeeds", async () => {
    const handlers: Record<string, Handler> = {
      ...defaultHandlers(),
      "scripts/build_dfs_pool_from_provider.py": () => {
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
          selected_slate_id: SLATE_ID, roster_feasibility_pass: true, player_count: 1,
          players: [{
            dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter",
            dk_positions: ["OF"], salary: 4000, projection: 10, ceiling: 18, risk_score: 30, confidence: 80,
            batting_order: 1, game_id: "g1", opponent: "TOR", lineup_status: "active", match_status: "matched",
            source_sha256: "abc123hash",
          }],
        });
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
          dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1, dk_games_matched_to_research: 1,
          source_provenance: "OFFICIAL_USER_UPLOAD",
          identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
          teams_awaiting_lineups: ["HOU", "LAA", "WSH"],
        });
        return ok();
      },
    };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("PARTIAL");
    expect(result.errors).toEqual([]); // not an error -- an expected, re-pullable in-progress state

    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("PARTIAL");
  });

  it("marks the slate ERROR when the player pool itself fails to build", async () => {
    const handlers = { ...defaultHandlers(), "scripts/build_dfs_pool_from_provider.py": () => fail("crash") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("ERROR");
    expect(result.errors[0]).toMatch(/player pool build failed/i);

    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("ERROR");
  });

  it("Milestone 31.1: recovers source_provenance/source_hash from disk on ERROR when the pool was actually written before a later step failed", async () => {
    const handlers: Record<string, Handler> = {
      ...defaultHandlers(),
      // Writes real pool/match-report files (with real provenance) --
      // exactly like a genuine success -- but still exits non-zero,
      // simulating a late-stage crash AFTER persistence.
      "scripts/build_dfs_pool_from_provider.py": () => {
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
          selected_slate_id: SLATE_ID, roster_feasibility_pass: true, player_count: 1,
          players: [{
            dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter",
            dk_positions: ["OF"], salary: 4000, projection: 10, ceiling: 18, risk_score: 30, confidence: 80,
            batting_order: 1, game_id: "g1", opponent: "TOR", lineup_status: "active", match_status: "matched",
            source_sha256: "recovered-hash-xyz",
          }],
        });
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
          dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1, dk_games_matched_to_research: 1,
          source_provenance: "OFFICIAL_USER_UPLOAD",
          identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
        });
        return fail("crashed after writing output");
      },
    };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("ERROR");

    const { getSlateStatus } = await import("../db/slateStatus");
    const status = (await getSlateStatus(DATE, SLATE_ID))!;
    expect(status.status).toBe("ERROR");
    expect(status.source_provenance).toBe("OFFICIAL_USER_UPLOAD");
    expect(status.source_hash).toBe("recovered-hash-xyz");
    expect(status.pool_path).toContain("dk_player_pool_");
  });

  it("leaves provenance/hash null on ERROR when nothing was ever written for this slate", async () => {
    const handlers = { ...defaultHandlers(), "scripts/fetch_dfs_slate.py": () => fail("no upload found") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("ERROR");

    const { getSlateStatus } = await import("../db/slateStatus");
    const status = (await getSlateStatus(DATE, SLATE_ID))!;
    expect(status.source_provenance).toBeNull();
    expect(status.source_hash).toBeNull();
  });

  it("still marks the slate READY when FantasyPros reports an api_error -- Native/AI are unaffected and the error is recorded, not swallowed or fatal", async () => {
    const handlers = { ...defaultHandlers(), "scripts/fetch_fantasypros_projections.py": () => ok(JSON.stringify({ status: "api_error", error: "401 Unauthorized" })) };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("FantasyPros API error"))).toBe(true);

    const { getSlateStatus } = await import("../db/slateStatus");
    const status = (await getSlateStatus(DATE, SLATE_ID))!;
    expect(status.status).toBe("READY");
    expect(status.native_snapshot_path).toContain("native_projection_");
    expect(status.ai_snapshot_path).toContain("ai_projection_");
  });

  it("still marks the slate READY when the FantasyPros script itself exits non-zero unexpectedly -- recorded as an error, never fatal to the slate", async () => {
    const handlers = { ...defaultHandlers(), "scripts/fetch_fantasypros_projections.py": () => fail("unexpected crash") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("FantasyPros fetch failed"))).toBe(true);

    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("READY");
  });

  it("does not record an error when FantasyPros is simply not configured -- that is a normal, expected outcome", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors).toEqual([]);
    expect(calls.map((c) => c.script)).toContain("scripts/fetch_fantasypros_projections.py");
  });

  it("passes --slate-id to the BlueCollar fetch script -- BlueCollar is always fetched scoped to ONE DK slate, never date-only", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    const call = calls.find((c) => c.script === "scripts/fetch_bluecollar_projections.py")!;
    expect(call.args).toEqual(["--date", DATE, "--slate-id", SLATE_ID]);
  });

  it("still marks the slate READY when BlueCollar reports an api_error -- Native/AI/ML are unaffected and the error is recorded, not swallowed or fatal", async () => {
    const handlers = { ...defaultHandlers(), "scripts/fetch_bluecollar_projections.py": () => ok(JSON.stringify({ status: "api_error", error: "HTTP 500" })) };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("BlueCollar API error"))).toBe(true);
    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("READY");
  });

  it("still marks the slate READY when BlueCollar's slate match is ambiguous/failed -- recorded as BlueCollar not updated, never fatal", async () => {
    const handlers = {
      ...defaultHandlers(),
      "scripts/fetch_bluecollar_projections.py": () => ok(JSON.stringify({ status: "slate_match_failed", reason: "BLUECOLLAR_SLATE_MATCH_AMBIGUOUS: ..." })),
    };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("BlueCollar not updated"))).toBe(true);
  });

  it("still marks the slate READY when the BlueCollar script itself exits non-zero unexpectedly -- recorded as an error, never fatal to the slate", async () => {
    const handlers = { ...defaultHandlers(), "scripts/fetch_bluecollar_projections.py": () => fail("unexpected crash") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("BlueCollar fetch failed"))).toBe(true);
    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("READY");
  });

  it("does not record an error when BlueCollar is simply not configured -- that is a normal, expected outcome", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors).toEqual([]);
    expect(calls.map((c) => c.script)).toContain("scripts/fetch_bluecollar_projections.py");
  });

  it("passes --date to the player identity refresh script", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    const call = calls.find((c) => c.script === "scripts/refresh_player_identity.py")!;
    expect(call.args).toEqual(["--date", DATE]);
  });

  it("still marks the slate READY when the player identity refresh script exits non-zero -- recorded as an error, never fatal to the slate", async () => {
    const handlers = { ...defaultHandlers(), "scripts/refresh_player_identity.py": () => fail("unexpected crash") };
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("Player identity refresh failed"))).toBe(true);
    const { getSlateStatus } = await import("../db/slateStatus");
    expect((await getSlateStatus(DATE, SLATE_ID))!.status).toBe("READY");
  });

  it("does not record an error when the player identity refresh succeeds normally", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors).toEqual([]);
    expect(calls.map((c) => c.script)).toContain("scripts/refresh_player_identity.py");
  });

  it("runs the player identity refresh BEFORE Native/AI projections, so they consult the freshest crosswalk", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    const scripts = calls.map((c) => c.script);
    expect(scripts.indexOf("scripts/refresh_player_identity.py")).toBeLessThan(scripts.indexOf("scripts/run_native_projection_engine.py"));
    expect(scripts.indexOf("scripts/refresh_player_identity.py")).toBeLessThan(scripts.indexOf("scripts/fetch_bluecollar_projections.py"));
  });

  it("M32.7: refreshes research_output (schedule/lineups) and re-scores both Agents BEFORE the pool is built", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    const scripts = calls.map((c) => c.script);
    const researchIdx = scripts.indexOf("scripts/build_research_package.py");
    const pitcherAgentIdx = scripts.indexOf("scripts/run_real_pitcher_agent.py");
    const batterAgentIdx = scripts.indexOf("scripts/run_real_batter_agent.py");
    const poolIdx = scripts.indexOf("scripts/build_dfs_pool_from_provider.py");
    expect(researchIdx).toBeLessThan(pitcherAgentIdx);
    expect(pitcherAgentIdx).toBeLessThan(batterAgentIdx);
    expect(batterAgentIdx).toBeLessThan(poolIdx);
  });

  it("M32.7: still marks the slate READY when the research package refresh fails -- recorded as an error, never fatal", async () => {
    const handlers = { ...defaultHandlers(), "scripts/build_research_package.py": () => fail("network hiccup") };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, []));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("Research package refresh failed"))).toBe(true);
  });

  it("M32.7: still marks the slate READY when Pitcher/Batter Agent scoring fails -- recorded as errors, never fatal", async () => {
    const handlers = {
      ...defaultHandlers(),
      "scripts/run_real_pitcher_agent.py": () => fail("pitcher agent crash"),
      "scripts/run_real_batter_agent.py": () => fail("batter agent crash"),
    };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, []));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("Pitcher Agent scoring failed"))).toBe(true);
    expect(result.errors.some((e) => e.includes("Batter Agent scoring failed"))).toBe(true);
  });

  it("M32.7: passes --date to the game environment (Vegas/weather) refresh script", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    const call = calls.find((c) => c.script === "scripts/build_game_environment_report.py")!;
    expect(call.args).toEqual(["--date", DATE]);
  });

  it("M32.7: still marks the slate READY when game environment refresh exits non-zero -- recorded as an error, never fatal", async () => {
    const handlers = { ...defaultHandlers(), "scripts/build_game_environment_report.py": () => fail("unexpected crash") };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, []));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors.some((e) => e.includes("Game environment refresh failed"))).toBe(true);
  });

  it("M32.7: does not record an error when game environment reports no_research -- a normal early-slate state", async () => {
    const handlers = { ...defaultHandlers(), "scripts/build_game_environment_report.py": () => ok(JSON.stringify({ status: "no_research", reason: "no research package yet" })) };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, []));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.status).toBe("READY");
    expect(result.errors).toEqual([]);
  });

  it("sets status to PROCESSING immediately, before the pipeline completes", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = defaultHandlers();
    let sawProcessing = false;
    const wrapped: Record<string, Handler> = {
      ...handlers,
      "scripts/fetch_dfs_slate.py": async (args) => {
        const { getSlateStatus } = await import("../db/slateStatus");
        sawProcessing = (await getSlateStatus(DATE, SLATE_ID))?.status === "PROCESSING";
        return handlers["scripts/fetch_dfs_slate.py"](args);
      },
    };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(wrapped, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(sawProcessing).toBe(true);
  });

  it("M32.7: produces a real change report -- lineups posted, hitters became eligible, native/AI generated", async () => {
    // Simulate a PRIOR refresh's leftover state: 3 teams still awaiting
    // lineups, 0 confirmed hitters, no native/AI generated yet.
    // loadLatestDkMatchReport(date, slateId) resolves its path FROM the
    // matching pool file's own selected_slate_id (see lib/loaders.ts),
    // so a matching pool file must exist too, not just the report.
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000000.json`, { selected_slate_id: SLATE_ID, player_count: 0, players: [] });
    writeJson(`dfs_input/${DATE}/dk_match_report_0000000000.json`, {
      dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1, dk_games_matched_to_research: 1,
      teams_awaiting_lineups: ["HOU", "LAA", "WSH"],
      eligibility: { confirmed_hitters: 0, optimizer_eligible: 0 },
    });

    const handlers: Record<string, Handler> = {
      ...defaultHandlers(),
      "scripts/build_dfs_pool_from_provider.py": () => {
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
          selected_slate_id: SLATE_ID, roster_feasibility_pass: true, player_count: 1,
          players: [{
            dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter",
            dk_positions: ["OF"], salary: 4000, projection: 10, ceiling: 18, risk_score: 30, confidence: 80,
            batting_order: 1, game_id: "g1", opponent: "TOR", lineup_status: "active", match_status: "matched",
            source_sha256: "abc123hash",
          }],
        });
        // Only HOU/LAA posted this refresh -- WSH is still awaiting.
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
          dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1, dk_games_matched_to_research: 1,
          source_provenance: "OFFICIAL_USER_UPLOAD",
          identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
          teams_awaiting_lineups: ["WSH"],
          eligibility: { confirmed_hitters: 18, optimizer_eligible: 18 },
        });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, []));

    const { runSlatePipeline } = await import("../slatePipeline");
    const result = await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(result.changeReport.lineupsPosted).toBe(2); // HOU, LAA
    expect(result.changeReport.hittersBecameEligible).toBe(18);
    expect(result.changeReport.stacksBecameReady).toBe(2);
    expect(result.changeReport.nativeGenerated).toBe(1); // defaultHandlers' native step writes 1 player
    expect(result.changeReport.aiGenerated).toBe(1);
  });
});
