import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../../orchestrator/pythonRunner";

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

function ok(stdout = "ok"): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}
function fail(stderr = "boom"): PythonRunResult {
  return { exitCode: 1, stdout: "", stderr, command: [] };
}

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
}

const DATE = "2026-08-12";

type Handler = (args: string[]) => PythonRunResult | Promise<PythonRunResult>;

function defaultHandlers(): Record<string, Handler> {
  return {
    "scripts/list_dfs_slates.py": () =>
      ok(
        JSON.stringify({
          status: "ready",
          reason: null,
          provider_name: "mock_dev_provider",
          is_mock: true,
          slates: [{ slate_id: "mock-main", slate_name: "Mock Main (Dev)", game_count: 15, start_time: null }],
        }),
      ),
    "scripts/fetch_dfs_slate.py": (args) => {
      const slateId = argValue(args, "--slate-id") ?? "mock-main";
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "ready",
        provider_name: "mock_dev_provider",
        selected_slate_id: slateId,
        slates: [{ slate_id: slateId, slate_name: "Mock Main (Dev)", game_count: 1, start_time: null }],
        players: [],
      });
      return ok();
    },
    "scripts/build_dfs_pool_from_provider.py": () => {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        roster_feasibility_pass: true,
        player_count: 2,
        players: [
          {
            dk_player_id: "d1",
            mlb_player_id: "h1",
            name: "Leadoff Hitter",
            team: "BOS",
            player_type: "hitter",
            dk_positions: ["OF"],
            salary: 4000,
            projection: 10,
            ceiling: 18,
            risk_score: 30,
            confidence: 80,
            batting_order: 1,
            game_id: "g1",
            opponent: "TOR",
            lineup_status: "active",
            match_status: "matched",
          },
          {
            dk_player_id: "d2",
            mlb_player_id: "p1",
            name: "Ace Pitcher",
            team: "TOR",
            player_type: "pitcher",
            dk_positions: ["P"],
            salary: 8000,
            projection: 20,
            ceiling: 32,
            risk_score: 25,
            confidence: 90,
            batting_order: null,
            game_id: "g1",
            opponent: "BOS",
            lineup_status: "active",
            match_status: "matched",
          },
        ],
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        dk_entries: 2,
        matched_to_mlb: 2,
        unmatched_count: 0,
        dk_games_total: 1,
      });
      return ok();
    },
    "scripts/project_dk_ownership.py": () => {
      writeJson(`ownership_predictions/${DATE}/ownership_${nextTs()}.json`, {
        players: [
          { dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 22, leverage_score: 5 },
          { dk_player_id: "d2", mlb_player_id: "p1", projected_ownership: 30, leverage_score: -2 },
        ],
      });
      return ok();
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

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-poolcache-"));
  tsCounter = 0;
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("listSlates", () => {
  it("parses a ready slate list from list_dfs_slates.py", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);

    expect(result.status).toBe("ready");
    expect(result.isMock).toBe(true);
    expect(result.providerName).toBe("mock_dev_provider");
    expect(result.slates).toEqual([{ slateId: "mock-main", slateName: "Mock Main (Dev)", gameCount: 15, startTime: null }]);
  });

  it("reports not_connected cleanly", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = {
      ...defaultHandlers(),
      "scripts/list_dfs_slates.py": () =>
        ok(JSON.stringify({ status: "not_connected", reason: "DFS_SALARY_PROVIDER is not set.", provider_name: null, is_mock: false, slates: [] })),
    };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);
    expect(result.status).toBe("not_connected");
    expect(result.slates).toEqual([]);
  });

  it("handles an unexpected script failure without throwing", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/list_dfs_slates.py": () => fail("traceback") };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);
    expect(result.status).toBe("unavailable");
  });
});

describe("loadPool", () => {
  it("builds the pool via fetch -> build -> ownership and returns joined player rows", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");

    expect(calls.map((c) => c.script)).toEqual([
      "scripts/fetch_dfs_slate.py",
      "scripts/build_dfs_pool_from_provider.py",
      "scripts/project_dk_ownership.py",
    ]);
    expect(argValue(calls[0].args, "--slate-id")).toBe("mock-main");

    expect(pool.activePlayers).toBe(2);
    expect(pool.pitcherCount).toBe(1);
    expect(pool.hitterCount).toBe(1);
    expect(pool.rosterFeasibilityPass).toBe(true);
    expect(pool.hasOwnership).toBe(true);
    expect(pool.isMock).toBe(true);
    expect(pool.slateGames).toBe(1);

    const hitter = pool.players.find((p) => p.dkPlayerId === "d1")!;
    expect(hitter.ownership).toBe(22);
    expect(hitter.leverage).toBe(5);
    expect(hitter.value).toBeCloseTo(2.5, 5); // 10 projection / (4000/1000)
  });

  it("caches the built pool -- a second call for the same slate does not re-invoke Python", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    await loadPool(DATE, "mock-main");
    const callCountAfterFirst = calls.length;
    await loadPool(DATE, "mock-main");
    expect(calls.length).toBe(callCountAfterFirst);
  });

  it("forceRefresh rebuilds the pool even when a cached entry exists", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    await loadPool(DATE, "mock-main");
    const callCountAfterFirst = calls.length;
    await loadPool(DATE, "mock-main", true);
    expect(calls.length).toBeGreaterThan(callCountAfterFirst);
  });

  it("throws a clear error when fetch_dfs_slate.py fails to produce a ready slate", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = {
      ...defaultHandlers(),
      "scripts/fetch_dfs_slate.py": () => {
        writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, { status: "invalid_slate_id", reason: "not found", slates: [] });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { loadPool } = await import("../poolCache");
    await expect(loadPool(DATE, "does-not-exist")).rejects.toThrow(/not ready/i);
  });

  it("throws when the pool-build step fails", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/build_dfs_pool_from_provider.py": () => fail("crash") };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { loadPool } = await import("../poolCache");
    await expect(loadPool(DATE, "mock-main")).rejects.toThrow(/failed to build player pool/i);
  });

  it("still returns a usable pool when ownership projection fails (best-effort)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/project_dk_ownership.py": () => fail("crash") };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");
    expect(pool.hasOwnership).toBe(false);
    expect(pool.players.every((p) => p.ownership === null)).toBe(true);
  });
});
