import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../orchestrator/pythonRunner";

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
  const { __resetDbForTests } = await import("../db/client");
  __resetDbForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
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
      "scripts/fetch_dfs_slate.py",
      "scripts/build_dfs_pool_from_provider.py",
      "scripts/project_dk_ownership.py",
      "scripts/run_native_projection_engine.py",
      "scripts/run_ai_projection_engine.py",
    ]);

    const { getSlateStatus } = await import("../db/slateStatus");
    const status = getSlateStatus(DATE, SLATE_ID)!;
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
    expect(getSlateStatus(DATE, SLATE_ID)!.status).toBe("PARTIAL");
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
    expect(getSlateStatus(DATE, SLATE_ID)!.status).toBe("ERROR");
  });

  it("sets status to PROCESSING immediately, before the pipeline completes", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = defaultHandlers();
    let sawProcessing = false;
    const wrapped: Record<string, Handler> = {
      ...handlers,
      "scripts/fetch_dfs_slate.py": async (args) => {
        const { getSlateStatus } = await import("../db/slateStatus");
        sawProcessing = getSlateStatus(DATE, SLATE_ID)?.status === "PROCESSING";
        return handlers["scripts/fetch_dfs_slate.py"](args);
      },
    };
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(wrapped, calls));

    const { runSlatePipeline } = await import("../slatePipeline");
    await runSlatePipeline(DATE, SLATE_ID, "Main");

    expect(sawProcessing).toBe(true);
  });
});
