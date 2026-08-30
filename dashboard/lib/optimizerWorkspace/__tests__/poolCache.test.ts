import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../../orchestrator/pythonRunner";

import { __resetStorageForTests } from "../../storage/getStorage";

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
          provider_type: "mock",
          is_mock: true,
          is_connected: true,
          source: "mock_explicit",
          slates: [{ slate_id: "mock-main", slate_name: "Mock Main (Dev)", game_count: 15, start_time: null }],
          slates_available: 1,
        }),
      ),
    "scripts/fetch_dfs_slate.py": (args) => {
      const slateId = argValue(args, "--slate-id") ?? "mock-main";
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "ready",
        provider_name: "mock_dev_provider",
        provider_type: "mock",
        is_mock: true,
        source: "mock_explicit",
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
            eligibility_status: "STARTING_HITTER",
            optimizer_eligible: true,
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
            eligibility_status: "STARTING_PITCHER",
            optimizer_eligible: true,
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
    "scripts/project_dk_ownership.py": (args) => {
      const slateId = argValue(args, "--slate-id");
      const dir = slateId ? `ownership_predictions/${DATE}/${slateId}` : `ownership_predictions/${DATE}`;
      writeJson(`${dir}/ownership_${nextTs()}.json`, {
        slate_id: slateId ?? null,
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
  __resetStorageForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
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
    expect(result.providerType).toBe("mock");
    expect(result.isConnected).toBe(true);
    expect(result.source).toBe("mock_explicit");
    expect(result.slatesAvailable).toBe(1);
    expect(result.slates).toEqual([
      { slateId: "mock-main", slateName: "Mock Main (Dev)", gameCount: 15, startTime: null, gameIds: [], playerCount: null },
    ]);
  });

  it("reports not_connected cleanly for an explicit, unrecognized provider name (never falls back silently)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = {
      ...defaultHandlers(),
      "scripts/list_dfs_slates.py": () =>
        ok(
          JSON.stringify({
            status: "not_connected",
            reason: "DFS_SALARY_PROVIDER='bogus' is not a recognized provider. Supported: ['mock'].",
            provider_name: null,
            provider_type: null,
            is_mock: false,
            is_connected: false,
            source: "explicit",
            slates: [],
            slates_available: 0,
          }),
        ),
    };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);
    expect(result.status).toBe("not_connected");
    expect(result.source).toBe("explicit");
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

  it("reuses a fresh already-fetched provider-slate document instead of calling list_dfs_slates.py again", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
      status: "ready",
      generated_at_utc: new Date().toISOString(),
      provider_name: "draftkings_unofficial",
      provider_type: "real",
      is_mock: false,
      source: "draftkings_unofficial_live",
      selected_slate_id: "main",
      slates: [{ slate_id: "main", slate_name: "Featured", game_count: 9, start_time: null }],
    });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);

    expect(calls.map((c) => c.script)).toEqual([]);
    expect(result.status).toBe("ready");
    expect(result.providerName).toBe("draftkings_unofficial");
    expect(result.isConnected).toBe(true);
    expect(result.slates).toEqual([
      { slateId: "main", slateName: "Featured", gameCount: 9, startTime: null, gameIds: [], playerCount: null },
    ]);
  });

  it("calls list_dfs_slates.py live when the existing provider-slate document is stale", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
      status: "ready",
      generated_at_utc: new Date(Date.now() - 60 * 60 * 1000).toISOString(), // 1 hour old
      provider_name: "draftkings_unofficial",
      is_mock: false,
      source: "draftkings_unofficial_live",
      selected_slate_id: "main",
      slates: [{ slate_id: "main", slate_name: "Featured", game_count: 9, start_time: null }],
    });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(DATE);

    expect(calls.map((c) => c.script)).toEqual(["scripts/list_dfs_slates.py"]);
    expect(result.providerName).toBe("mock_dev_provider");
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
    expect(pool.providerSource).toBe("mock_explicit");
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

  it("reuses a fresh already-fetched provider-slate document for this exact slate instead of calling fetch_dfs_slate.py again", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
      status: "ready",
      generated_at_utc: new Date().toISOString(),
      provider_name: "draftkings_unofficial",
      provider_type: "real",
      is_mock: false,
      source: "draftkings_unofficial_live",
      selected_slate_id: "mock-main",
      slates: [{ slate_id: "mock-main", slate_name: "Mock Main (Dev)", game_count: 1, start_time: null }],
      players: [],
    });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");

    expect(calls.map((c) => c.script)).toEqual(["scripts/build_dfs_pool_from_provider.py", "scripts/project_dk_ownership.py"]);
    expect(pool.providerSource).toBe("draftkings_unofficial_live");
  });

  it("does not reuse a fresh provider-slate document fetched for a DIFFERENT slate", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
      status: "ready",
      generated_at_utc: new Date().toISOString(),
      provider_name: "draftkings_unofficial",
      is_mock: false,
      source: "draftkings_unofficial_live",
      selected_slate_id: "other-slate",
      slates: [],
      players: [],
    });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    await loadPool(DATE, "mock-main");

    expect(calls.map((c) => c.script)).toContain("scripts/fetch_dfs_slate.py");
  });

  it("does not reuse a stale provider-slate document even for the same slate", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
      status: "ready",
      generated_at_utc: new Date(Date.now() - 60 * 60 * 1000).toISOString(), // 1 hour old
      provider_name: "draftkings_unofficial",
      is_mock: false,
      source: "draftkings_unofficial_live",
      selected_slate_id: "mock-main",
      slates: [],
      players: [],
    });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    await loadPool(DATE, "mock-main");

    expect(calls.map((c) => c.script)).toContain("scripts/fetch_dfs_slate.py");
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

  it("joins Native Projection data by mlbPlayerId when a snapshot exists (Milestone 23)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    writeJson(`native_projection_snapshots/${DATE}/native_projection_20260812T180000.json`, {
      slate_date: DATE, generated_at: `${DATE}T18:00:00Z`, model_version: "1.0.0",
      pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
      player_count: 2,
      players: [
        { player_id: "h1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter", native_projection: 9.5, native_ceiling: 15.0, native_floor: 4.0, confidence: 70, reasons: ["r1"] },
        { player_id: "p1", name: "Ace Pitcher", team: "TOR", player_type: "pitcher", native_projection: 22.5, native_ceiling: 30.0, native_floor: 14.0, confidence: 85, reasons: ["r2"] },
      ],
      warnings: [],
    });

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");

    expect(pool.hasNativeProjections).toBe(true);
    const hitter = pool.players.find((p) => p.dkPlayerId === "d1")!;
    expect(hitter.nativeProjection).toBe(9.5);
    expect(hitter.nativeCeiling).toBe(15.0);
    expect(hitter.nativeDelta).toBeCloseTo(-0.5, 5); // 9.5 - 10 (independent projection)
    expect(hitter.nativeConfidence).toBe(70);
    expect(hitter.nativeReasons).toEqual(["r1"]);
  });

  it("Milestone 26: two slates sharing a date never leak each other's ownership (confirmed real bug fix)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers: Record<string, Handler> = {
      ...defaultHandlers(),
      "scripts/build_dfs_pool_from_provider.py": (args) => {
        const providerSlatePath = argValue(args, "--provider-slate")!;
        const providerDoc = JSON.parse(fs.readFileSync(providerSlatePath, "utf-8")) as { selected_slate_id: string };
        const slateId = providerDoc.selected_slate_id;
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
          roster_feasibility_pass: true,
          player_count: 1,
          players: [
            {
              dk_player_id: slateId, mlb_player_id: `p-${slateId}`, name: `${slateId} player`, team: "BOS",
              player_type: "pitcher", dk_positions: ["P"], salary: 8000, projection: 20, ceiling: 32,
              risk_score: 25, confidence: 90, batting_order: null, game_id: "g1", opponent: "TOR",
              lineup_status: "active", match_status: "matched",
              eligibility_status: "STARTING_PITCHER", optimizer_eligible: true,
            },
          ],
        });
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, { dk_entries: 1, matched_to_mlb: 1, unmatched_count: 0, dk_games_total: 1 });
        return ok();
      },
      "scripts/fetch_dfs_slate.py": (args) => {
        const slateId = argValue(args, "--slate-id") ?? "mock-main";
        writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
          status: "ready", provider_name: "mock_dev_provider", provider_type: "mock", is_mock: true,
          source: "mock_explicit", selected_slate_id: slateId,
          slates: [{ slate_id: slateId, slate_name: slateId, game_count: 1, start_time: null }], players: [],
        });
        return ok();
      },
      "scripts/project_dk_ownership.py": (args) => {
        const slateId = argValue(args, "--slate-id")!;
        const own = slateId === "turbo" ? 55 : 12;
        writeJson(`ownership_predictions/${DATE}/${slateId}/ownership_${nextTs()}.json`, {
          slate_id: slateId,
          players: [{ dk_player_id: slateId, mlb_player_id: `p-${slateId}`, projected_ownership: own, leverage_score: 0 }],
        });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { loadPool } = await import("../poolCache");
    const main = await loadPool(DATE, "main");
    const turbo = await loadPool(DATE, "turbo");

    expect(main.players[0].ownership).toBe(12);
    expect(turbo.players[0].ownership).toBe(55);
    // Loading Main again after Turbo must still show Main's own ownership, not Turbo's.
    const mainAgain = await loadPool(DATE, "main", true);
    expect(mainAgain.players[0].ownership).toBe(12);
  });

  it("hasNativeProjections is false and native fields stay null when no snapshot exists", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");
    expect(pool.hasNativeProjections).toBe(false);
    expect(pool.players.every((p) => p.nativeProjection === null)).toBe(true);
  });

  it("joins FantasyPros data by mlbPlayerId when a snapshot exists, never touching the independent projection", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260812T180000.json`, {
      slate_date: DATE, retrieved_at: `${DATE}T18:00:00Z`, hitter_count: 1, pitcher_count: 0,
      hitters_matched: 1, pitchers_matched: 0, public_api_limited: true, api_tier: "free",
      players: [
        {
          fantasypros_id: "1", name: "Leadoff Hitter", team: "BOS", player_type: "hitter", yahoo_id: null,
          raw_stats: {}, dk_points: 8.9, dk_points_breakdown: {}, match_status: "matched",
          match_confidence: "name_team_exact", mlb_player_id: "h1", candidate_mlb_ids: [], candidate_names: [],
        },
      ],
    });

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");

    expect(pool.hasFantasyProsProjections).toBe(true);
    const hitter = pool.players.find((p) => p.dkPlayerId === "d1")!;
    expect(hitter.fantasyProsProjection).toBe(8.9);
    expect(hitter.fantasyProsMatchStatus).toBe("matched");
    expect(hitter.projection).not.toBe(8.9); // independent projection is unaffected by FantasyPros
  });

  it("hasFantasyProsProjections is false and fantasyPros fields stay null when no snapshot exists", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { loadPool } = await import("../poolCache");
    const pool = await loadPool(DATE, "mock-main");
    expect(pool.hasFantasyProsProjections).toBe(false);
    expect(pool.players.every((p) => p.fantasyProsProjection === null)).toBe(true);
  });
});
