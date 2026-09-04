import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getTodayEasternDate } from "../../currentDate";
import type { PythonRunner, PythonRunResult } from "../pythonRunner";

import { __resetStorageForTests } from "../../storage/getStorage";

// This file never spawns a real Python process or touches the network --
// every script invocation is intercepted by __setPythonRunnerForTests and
// answered by an in-memory fake that writes the same fixture-shaped JSON
// artifacts the real scripts would, so the orchestrator's own artifact-
// diffing / summary-building logic is exercised for real.

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
function noop(): PythonRunResult {
  return { exitCode: 0, stdout: "nothing written", stderr: "", command: [] };
}

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
}

type Handler = (args: string[]) => PythonRunResult | Promise<PythonRunResult>;

// startRefresh() always resolves the slate date via getTodayEasternDate()
// internally (never client-supplied) -- fixtures must use the SAME value
// so the run's slateDate matches where these fake handlers write, or
// every fingerprint check "sees" a different date and reports missing.
const DATE = getTodayEasternDate();

function defaultHandlers(): Record<string, Handler> {
  return {
    "scripts/build_research_package.py": () => {
      writeJson(`research_output/${DATE}/slate.json`, {
        slate_date: DATE,
        game_ids: ["g1"],
        team_ids: ["BOS", "TOR"],
        counts: { games: 1, teams: 2, pitchers: 2, batters: 2 },
        notes: [],
      });
      return ok();
    },
    "scripts/run_real_pitcher_agent.py": () => {
      writeJson(`predictions/${DATE}/pitcher_board_${nextTs()}.json`, {
        slate_date: DATE,
        generated_at_utc: `${DATE}T18:00:00+00:00`,
        model_version: "v1",
        pitcher_count: 2,
        pitchers: [],
      });
      return ok();
    },
    "scripts/run_real_batter_agent.py": () => {
      writeJson(`predictions/${DATE}/batter_board_${nextTs()}.json`, {
        slate_date: DATE,
        generated_at_utc: `${DATE}T18:05:00+00:00`,
        model_version: "v1",
        hitter_count: 2,
        missing_lineup_game_ids: [],
        hitters: [
          { player_id: "h1", name: "Leadoff Hitter", team: "BOS", opponent: "TOR", game_id: "g1", batting_order: 1 },
          { player_id: "h2", name: "Cleanup Hitter", team: "BOS", opponent: "TOR", game_id: "g1", batting_order: 4 },
        ],
      });
      return ok();
    },
    "scripts/fetch_dfs_slate.py": (args) => {
      const slateId = argValue(args, "--slate-id") ?? "mock-main";
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        slate_date: DATE,
        status: "ready",
        reason: null,
        provider_name: "mock_dev_provider",
        slates: [{ slate_id: slateId, slate_name: "Mock Main (Dev)", game_count: 1, start_time: null }],
        selected_slate_id: slateId,
        players: [
          { external_player_id: "d1", name: "Leadoff Hitter", team: "BOS", salary: 4200, position_eligibility: ["OF"], game: "TOR@BOS 7:05PM ET" },
          { external_player_id: "d2", name: "Cleanup Hitter", team: "BOS", salary: 5200, position_eligibility: ["1B"], game: "TOR@BOS 7:05PM ET" },
        ],
      });
      return ok();
    },
    "scripts/build_dfs_pool_from_provider.py": () => {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        slate_date: DATE,
        generated_at_utc: `${DATE}T18:10:00+00:00`,
        roster_feasibility_pass: true,
        player_count: 2,
        players: [
          { dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", team: "BOS", salary: 4200, projection: 9, lineup_status: "active", match_status: "matched" },
          { dk_player_id: "d2", mlb_player_id: "h2", name: "Cleanup Hitter", team: "BOS", salary: 5200, projection: 8, lineup_status: "active", match_status: "matched" },
        ],
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        dk_entries: 2,
        matched_to_mlb: 2,
        unmatched_count: 0,
        salary_coverage_percent: 100,
        position_coverage_percent: 100,
        dk_games_total: 1,
      });
      return ok();
    },
    "scripts/project_dk_ownership.py": () => {
      writeJson(`ownership_predictions/${DATE}/ownership_${nextTs()}.json`, {
        slate_date: DATE,
        generated_at_utc: `${DATE}T18:15:00+00:00`,
        model_version: "v1",
        player_count: 2,
        players: [
          { dk_player_id: "d1", mlb_player_id: "h1", name: "Leadoff Hitter", projected_ownership: 20 },
          { dk_player_id: "d2", mlb_player_id: "h2", name: "Cleanup Hitter", projected_ownership: 10 },
        ],
        team_popularity: {},
        normalization_checks: {},
      });
      return ok();
    },
    "scripts/optimize_dk_lineups.py": (args) => {
      const objective = argValue(args, "--objective");
      writeJson(`lineups/${DATE}/dk_lineups_${nextTs()}.json`, {
        slate_date: DATE,
        generated_at: `${DATE}T18:20:00+00:00`,
        settings: { objective_mode: objective },
        lineups_requested: 20,
        lineups_generated: 20,
        stopped_reason: null,
        lineups: [{ index: 0, assignments: [{ slot: "OF", dk_player_id: "d1", name: "Leadoff Hitter" }], salary: 9400, projection: 17, ceiling: 31 }],
      });
      return ok();
    },
    "scripts/run_projection_adjustment.py": () => ok(JSON.stringify({ status: "no_baseline", reason: "No external baseline snapshot found." })),
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
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-orchestrator-"));
  tsCounter = 0;
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  process.env.MLB_DFS_RUNSTATE_DIR = path.join(tmpDir, ".runstate");
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../pythonRunner");
  const { __resetOrchestratorStateForTests } = await import("../runner");
  __resetPythonRunnerForTests();
  __resetOrchestratorStateForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  delete process.env.MLB_DFS_RUNSTATE_DIR;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("one-click orchestration: happy path", () => {
  it(
    "runs every pipeline step in order and completes with outcome ready",
    async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      const { __setPythonRunnerForTests } = await import("../pythonRunner");
      __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

      const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");
      const started = startRefresh();
      expect(started.accepted).toBe(true);
      await __waitForActiveRunToSettleForTests();

      const run = started.run;
      expect(run.status).toBe("completed");
      expect(run.outcome).toBe("ready");
      expect(run.steps.every((s) => s.status === "ready")).toBe(true);

      // Pipeline ordering: research -> pitchers -> batters -> dfs salaries ->
      // player pool -> ownership -> external projection refresh (Milestone 19,
      // best-effort) -> optimizer x3 (Projection, Balanced, Leverage).
      expect(calls.map((c) => c.script)).toEqual([
        "scripts/build_research_package.py",
        "scripts/run_real_pitcher_agent.py",
        "scripts/run_real_batter_agent.py",
        "scripts/fetch_dfs_slate.py",
        "scripts/build_dfs_pool_from_provider.py",
        "scripts/project_dk_ownership.py",
        "scripts/run_projection_adjustment.py",
        "scripts/optimize_dk_lineups.py",
        "scripts/optimize_dk_lineups.py",
        "scripts/optimize_dk_lineups.py",
      ]);
      const optimizerObjectives = calls.filter((c) => c.script === "scripts/optimize_dk_lineups.py").map((c) => argValue(c.args, "--objective"));
      expect(optimizerObjectives).toEqual(["projection", "balanced", "leverage"]);

      const summary = run.summary!;
      expect(summary.mlbGames).toBe(1);
      expect(summary.pitcherCount).toBe(2);
      expect(summary.hitterCount).toBe(2);
      expect(summary.dkEntries).toBe(2);
      expect(summary.matchedToMlb).toBe(2);
      expect(summary.rosterFeasibilityPass).toBe(true);
      expect(summary.ownershipReady).toBe(true);
      expect(summary.lineupCounts).toEqual({ projection: 20, balanced: 20, leverage: 20 });
      expect(summary.providerName).toBe("mock_dev_provider");
      expect(summary.selectedSlateId).toBe("mock-main");
      expect(summary.externalProjectionStatus).toBe("no_baseline");

      // No manual DK CSV upload anywhere in this flow -- every arg passed to
      // every script came from server-resolved state (today's date, a
      // discovered slate id, an already-saved pool path), never a file path
      // supplied by a browser upload.
      for (const call of calls) {
        expect(call.args).not.toContain("--csv");
      }
    },
    15000,
  );

  it("a second completed run the same day gets a non-null change report referencing the first run", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));

    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");
    const first = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(first.run.status).toBe("completed");

    const second = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(second.run.status).toBe("completed");
    expect(second.run.changeReport).not.toBeNull();
    expect(second.run.changeReport!.previousRunId).toBe(first.run.runId);
  }, 20000);
});

describe("DFS provider fallback states", () => {
  async function runWithFetchOverride(fetchHandler: Handler) {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/fetch_dfs_slate.py": fetchHandler };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");
    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    return { run: started.run, calls };
  }

  it("completes Research/Pitchers/Batters then stops cleanly with dfs_not_connected when no provider is configured", async () => {
    const { run, calls } = await runWithFetchOverride(() => {
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "not_connected",
        reason: "DFS_SALARY_PROVIDER is not set.",
        provider_name: null,
        slates: [],
        players: [],
      });
      return ok();
    });

    expect(run.status).toBe("failed");
    expect(run.outcome).toBe("dfs_not_connected");
    const byId = Object.fromEntries(run.steps.map((s) => [s.id, s]));
    expect(byId.research.status).toBe("ready");
    expect(byId.pitchers.status).toBe("ready");
    expect(byId.batters.status).toBe("ready");
    expect(byId.dfsSalaries.status).toBe("failed");
    expect(byId.dfsSalaries.message).toMatch(/DFS_SALARY_PROVIDER/);
    expect(byId.playerPool.status).toBe("skipped");
    expect(byId.ownership.status).toBe("skipped");
    expect(byId.optimizer.status).toBe("skipped");
    expect(calls.map((c) => c.script)).not.toContain("scripts/build_dfs_pool_from_provider.py");
  });

  it("reports dfs_auth_failed distinctly from dfs_not_connected", async () => {
    const { run } = await runWithFetchOverride(() => {
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "auth_failed",
        reason: "DFS_PROVIDER_API_KEY was rejected.",
        provider_name: "acme_dfs",
        slates: [],
        players: [],
      });
      return ok();
    });
    expect(run.outcome).toBe("dfs_auth_failed");
  });

  it("reports dfs_unavailable when the script exits non-zero unexpectedly", async () => {
    const { run } = await runWithFetchOverride(() => fail("connection reset"));
    expect(run.outcome).toBe("dfs_unavailable");
    const byId = Object.fromEntries(run.steps.map((s) => [s.id, s]));
    expect(byId.dfsSalaries.stderrTail).toContain("connection reset");
  });
});

describe("multi-slate selection and resume", () => {
  it("pauses for slate selection, rejects an unknown slate id, and resumes with a valid one", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers: Record<string, Handler> = {
      ...defaultHandlers(),
      "scripts/fetch_dfs_slate.py": (args) => {
        const slateId = argValue(args, "--slate-id");
        if (!slateId) {
          writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
            status: "needs_selection",
            reason: null,
            provider_name: "mock_dev_provider",
            slates: [
              { slate_id: "main", slate_name: "Main", game_count: 8, start_time: "7:05PM ET" },
              { slate_id: "turbo", slate_name: "Turbo", game_count: 4, start_time: "8:10PM ET" },
            ],
            players: [],
          });
          return ok();
        }
        writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
          status: "ready",
          reason: null,
          provider_name: "mock_dev_provider",
          slates: [{ slate_id: slateId, slate_name: slateId, game_count: 8, start_time: null }],
          selected_slate_id: slateId,
          players: [
            { external_player_id: "d1", name: "Leadoff Hitter", team: "BOS", salary: 4200, position_eligibility: ["OF"], game: "TOR@BOS 7:05PM ET" },
            { external_player_id: "d2", name: "Cleanup Hitter", team: "BOS", salary: 5200, position_eligibility: ["1B"], game: "TOR@BOS 7:05PM ET" },
          ],
        });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));

    const { startRefresh, resumeWithSlateSelection, __waitForActiveRunToSettleForTests, getCurrentRun } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.status).toBe("needs_selection");
    expect(started.run.outcome).toBe("needs_slate_selection");
    expect(started.run.slateOptions).toHaveLength(2);
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    expect(byId.dfsSalaries.status).toBe("needs_input");

    const badResume = resumeWithSlateSelection("not-a-real-slate");
    expect(badResume.ok).toBe(false);

    const goodResume = resumeWithSlateSelection("turbo");
    expect(goodResume.ok).toBe(true);
    await __waitForActiveRunToSettleForTests();

    const finalRun = getCurrentRun()!;
    expect(finalRun.status).toBe("completed");
    expect(finalRun.outcome).toBe("ready");
    expect(finalRun.summary!.selectedSlateId).toBe("turbo");

    // fetch_dfs_slate.py should have been called exactly twice: once with no
    // --slate-id (discovery), once with --slate-id turbo (the user's choice).
    const fetchCalls = calls.filter((c) => c.script === "scripts/fetch_dfs_slate.py");
    expect(fetchCalls).toHaveLength(2);
    expect(argValue(fetchCalls[0].args, "--slate-id")).toBeUndefined();
    expect(argValue(fetchCalls[1].args, "--slate-id")).toBe("turbo");
  }, 15000);
});

describe("player pool / roster / ownership / optimizer failure states", () => {
  it("stops before ownership/optimizer with player_matching_failure when zero DFS entries match MLB identities", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = {
      ...defaultHandlers(),
      "scripts/build_dfs_pool_from_provider.py": () => {
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, { roster_feasibility_pass: false, player_count: 0, players: [] });
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, { dk_entries: 2, matched_to_mlb: 0, unmatched_count: 2 });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.status).toBe("failed");
    expect(started.run.outcome).toBe("player_matching_failure");
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    expect(byId.ownership.status).toBe("skipped");
    expect(byId.optimizer.status).toBe("skipped");
  });

  it("stops with roster_infeasible when players matched but no legal roster can be built", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = {
      ...defaultHandlers(),
      "scripts/build_dfs_pool_from_provider.py": () => {
        const ts = nextTs();
        writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, { roster_feasibility_pass: false, player_count: 2, players: [] });
        writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, { dk_entries: 2, matched_to_mlb: 2, unmatched_count: 0 });
        return ok();
      },
    };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.outcome).toBe("roster_infeasible");
  });

  it("reports ownership_failure when the ownership script exits 0 but writes nothing new", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/project_dk_ownership.py": () => noop() };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.outcome).toBe("ownership_failure");
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    expect(byId.optimizer.status).toBe("skipped");
  });

  it(
    "reports optimizer_infeasible when one objective fails, still recording the objectives that succeeded",
    async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      const handlers = {
        ...defaultHandlers(),
        "scripts/optimize_dk_lineups.py": (args: string[]) => {
          if (argValue(args, "--objective") === "leverage") return fail("infeasible under salary cap");
          const ts = nextTs();
          writeJson(`lineups/${DATE}/dk_lineups_${ts}.json`, {
            settings: { objective_mode: argValue(args, "--objective") },
            lineups_generated: 20,
            lineups: [],
          });
          return ok();
        },
      };
      const { __setPythonRunnerForTests } = await import("../pythonRunner");
      __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
      const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

      const started = startRefresh();
      await __waitForActiveRunToSettleForTests();
      expect(started.run.outcome).toBe("optimizer_infeasible");
      const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
      expect(byId.optimizer.message).toMatch(/leverage/i);
    },
    15000,
  );
});

describe("concurrency lock", () => {
  it("rejects a second refresh while one is already running, then accepts a new one once it settles", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const first = startRefresh();
    const second = startRefresh();
    expect(first.accepted).toBe(true);
    expect(second.accepted).toBe(false);
    expect(second.conflict).toBe(true);
    expect(second.run.runId).toBe(first.run.runId);

    await __waitForActiveRunToSettleForTests();

    const third = startRefresh();
    expect(third.accepted).toBe(true);
    expect(third.run.runId).not.toBe(first.run.runId);
    await __waitForActiveRunToSettleForTests();
  }, 20000);
});

describe("mlb_data_failure and disk-persisted state", () => {
  it("marks research failed and stops the whole run when the research script produces no artifact", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/build_research_package.py": () => noop() };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.outcome).toBe("mlb_data_failure");
    expect(calls.map((c) => c.script)).toEqual(["scripts/build_research_package.py"]);
  });

  it("persists run state to disk so it can be read back after the in-memory pointer is cleared", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests, __resetOrchestratorStateForTests, getCurrentRun } = await import("../runner");

    const started = startRefresh();
    await __waitForActiveRunToSettleForTests();
    expect(started.run.status).toBe("completed");

    // Simulate a fresh process losing its in-memory pointers -- the GET
    // status endpoint must still be able to show the last known state.
    __resetOrchestratorStateForTests();
    const recovered = getCurrentRun();
    expect(recovered).not.toBeNull();
    expect(recovered!.runId).toBe(started.run.runId);
    expect(recovered!.status).toBe("completed");
  }, 15000);
});

// Pre-seeds every pregame artifact EXCEPT the batter snapshot, so a smart
// refresh targeting "everything" (Milestone 16's "Refresh Missing Data")
// has exactly one real gap to fill.
function seedEverythingExceptBatters() {
  writeJson(`research_output/${DATE}/slate.json`, { slate_date: DATE, counts: { games: 1 } });
  writeJson(`predictions/${DATE}/pitcher_board_0000000001.json`, { slate_date: DATE, pitcher_count: 2 });
  writeJson(`dfs_input/${DATE}/provider_slate_0000000001.json`, {
    status: "ready",
    provider_name: "mock_dev_provider",
    selected_slate_id: "mock-main",
    slates: [{ slate_id: "mock-main", slate_name: "Mock Main (Dev)", game_count: 1, start_time: null }],
    players: [],
  });
  writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { roster_feasibility_pass: true, player_count: 2, players: [] });
  writeJson(`dfs_input/${DATE}/dk_match_report_0000000001.json`, { dk_entries: 2, matched_to_mlb: 2, unmatched_count: 0 });
  writeJson(`ownership_predictions/${DATE}/ownership_0000000001.json`, { players: [] });
  writeJson(`lineups/${DATE}/dk_lineups_0000000001.json`, { lineups_generated: 20, lineups: [] });
}

describe("smart (missing-data-only) refresh", () => {
  it("skips a step whose artifact already exists instead of re-invoking its script", async () => {
    writeJson(`research_output/${DATE}/slate.json`, { slate_date: DATE, counts: { games: 1 } });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh({ targetSteps: ["research"], smart: true });
    await __waitForActiveRunToSettleForTests();

    expect(calls.map((c) => c.script)).not.toContain("scripts/build_research_package.py");
    const research = started.run.steps.find((s) => s.id === "research")!;
    expect(research.status).toBe("ready");
    expect(research.message).toBe("Already up to date.");
    expect(started.run.status).toBe("completed");
    expect(started.run.mode).toBe("smart");
    expect(started.run.requestedSteps).toEqual(["research"]);
  });

  it("a targeted refresh only touches its own dependency chain -- unrelated steps are marked skipped, not attempted", async () => {
    writeJson(`research_output/${DATE}/slate.json`, { slate_date: DATE, counts: { games: 1 } });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    // "Generate Batter Research": target = batters only.
    const started = startRefresh({ targetSteps: ["batters"], smart: true });
    await __waitForActiveRunToSettleForTests();

    expect(calls.map((c) => c.script)).toEqual(["scripts/run_real_batter_agent.py"]);
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    expect(byId.research.status).toBe("ready"); // already existed, skipped-as-ready
    expect(byId.batters.status).toBe("ready"); // actually ran
    expect(byId.pitchers.status).toBe("skipped");
    expect(byId.dfsSalaries.status).toBe("skipped");
    expect(byId.playerPool.status).toBe("skipped");
    expect(byId.ownership.status).toBe("skipped");
    expect(byId.optimizer.status).toBe("skipped");
    expect(byId.pitchers.message).toBe("Not required for this action.");
    expect(started.run.status).toBe("completed");
  });

  it("'Refresh Missing Data' (target = everything) runs only the one genuinely missing step when everything else is already ready", async () => {
    seedEverythingExceptBatters();
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh({ targetSteps: ["optimizer"], smart: true });
    await __waitForActiveRunToSettleForTests();

    // Only the Batter Agent script should have actually been invoked --
    // every other already-ready step must NOT be unnecessarily rebuilt.
    expect(calls.map((c) => c.script)).toEqual(["scripts/run_real_batter_agent.py"]);
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    for (const id of ["research", "pitchers", "dfsSalaries", "playerPool", "ownership", "optimizer"]) {
      expect(byId[id].status).toBe("ready");
      expect(byId[id].message).toBe("Already up to date.");
    }
    expect(byId.batters.status).toBe("ready");
    expect(byId.batters.message).toBeNull(); // actually ran, normal success message shape
    expect(started.run.status).toBe("completed");
    expect(started.run.outcome).toBe("ready");
  });

  it("runs dependencies in correct pipeline order when nothing is ready yet", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh({ targetSteps: ["playerPool"], smart: true });
    await __waitForActiveRunToSettleForTests();

    expect(calls.map((c) => c.script)).toEqual([
      "scripts/build_research_package.py",
      "scripts/run_real_pitcher_agent.py",
      "scripts/run_real_batter_agent.py",
      "scripts/fetch_dfs_slate.py",
      "scripts/build_dfs_pool_from_provider.py",
    ]);
    const byId = Object.fromEntries(started.run.steps.map((s) => [s.id, s]));
    expect(byId.ownership.status).toBe("skipped");
    expect(byId.optimizer.status).toBe("skipped");
    expect(started.run.status).toBe("completed");
  });

  it("a failed dependency blocks every downstream step from even being attempted", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const handlers = { ...defaultHandlers(), "scripts/run_real_batter_agent.py": () => fail("batter agent crashed") };
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh({ targetSteps: ["playerPool"], smart: true });
    await __waitForActiveRunToSettleForTests();

    expect(started.run.status).toBe("failed");
    expect(started.run.outcome).toBe("batter_agent_failure");
    expect(calls.map((c) => c.script)).toEqual(["scripts/build_research_package.py", "scripts/run_real_pitcher_agent.py", "scripts/run_real_batter_agent.py"]);
    expect(calls.map((c) => c.script)).not.toContain("scripts/fetch_dfs_slate.py");
    expect(calls.map((c) => c.script)).not.toContain("scripts/build_dfs_pool_from_provider.py");
  });

  it("a full (non-smart) refresh still rebuilds already-ready artifacts unconditionally -- the original Refresh Today's Slate behavior is unchanged", async () => {
    writeJson(`research_output/${DATE}/slate.json`, { slate_date: DATE, counts: { games: 1 } });
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner(defaultHandlers(), calls));
    const { startRefresh, __waitForActiveRunToSettleForTests } = await import("../runner");

    const started = startRefresh(); // no options -- the plain "Refresh Today's Slate" button
    await __waitForActiveRunToSettleForTests();

    expect(calls.map((c) => c.script)).toContain("scripts/build_research_package.py");
    expect(started.run.mode).toBe("full");
    expect(started.run.requestedSteps).toBeNull();
    const research = started.run.steps.find((s) => s.id === "research")!;
    expect(research.message).not.toBe("Already up to date.");
  }, 15000);
});
