import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../../orchestrator/pythonRunner";
import type { OptimizerBuildRequest } from "../types";

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

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
}
function argValues(args: string[], flag: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < args.length; i++) if (args[i] === flag) out.push(args[i + 1]);
  return out;
}

const DATE = "2026-08-12";

type Handler = (args: string[]) => PythonRunResult | Promise<PythonRunResult>;

function baseRequest(overrides: Partial<OptimizerBuildRequest> = {}): OptimizerBuildRequest {
  return {
    date: DATE,
    slateId: "mock-main",
    lineups: 20,
    objective: "projection",
    locks: [],
    exclusions: [],
    maxExposure: {},
    stackSize: null,
    stackTeam: null,
    allowPitcherVsHitter: false,
    minSalary: null,
    minUnique: 2,
    minConfidence: null,
    maxPlayerRisk: null,
    ...overrides,
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

async function seedCachedPool(calls: Array<{ script: string; args: string[] }>) {
  const handlers: Record<string, Handler> = {
    "scripts/fetch_dfs_slate.py": () => {
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "ready",
        provider_name: "mock_dev_provider",
        selected_slate_id: "mock-main",
        slates: [{ slate_id: "mock-main", slate_name: "Mock Main (Dev)", game_count: 1, start_time: null }],
        players: [],
      });
      return ok();
    },
    "scripts/build_dfs_pool_from_provider.py": () => {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, { roster_feasibility_pass: true, player_count: 0, players: [] });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, { dk_entries: 0, matched_to_mlb: 0 });
      return ok();
    },
    "scripts/project_dk_ownership.py": () => {
      writeJson(`ownership_predictions/${DATE}/ownership_${nextTs()}.json`, { players: [] });
      return ok();
    },
  };
  const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __setPythonRunnerForTests(makeFakeRunner(handlers, calls));
  const { loadPool } = await import("../poolCache");
  await loadPool(DATE, "mock-main");
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-buildrunner-"));
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

describe("validateBuildRequest", () => {
  it("returns a clear error when no pool has been loaded for the slate", async () => {
    const { validateBuildRequest } = await import("../buildRunner");
    const errors = await validateBuildRequest(baseRequest());
    expect(errors[0]).toMatch(/select a slate first/i);
  });

  it("parses the errors array printed by --validate-only", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);

    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        { "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: ["--stack-team ZZZ only has 0 eligible hitter(s) (need 5)."] })) },
        calls,
      ),
    );

    const { validateBuildRequest } = await import("../buildRunner");
    const errors = await validateBuildRequest(baseRequest({ stackSize: 5, stackTeam: "ZZZ" }));
    expect(errors).toEqual(["--stack-team ZZZ only has 0 eligible hitter(s) (need 5)."]);

    const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
    expect(call.args).toContain("--validate-only");
    expect(argValue(call.args, "--stack-size")).toBe("5");
    expect(argValue(call.args, "--stack-team")).toBe("ZZZ");
  });

  it("returns [] when validation finds nothing wrong", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: [] })) }, calls));

    const { validateBuildRequest } = await import("../buildRunner");
    expect(await validateBuildRequest(baseRequest())).toEqual([]);
  });
});

describe("buildLineups", () => {
  it("builds argv with every constraint field correctly, including --interactive", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);

    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/optimize_dk_lineups.py": (args) => {
            if (args.includes("--validate-only")) return ok(JSON.stringify({ errors: [] }));
            writeJson(`lineups/${DATE}/dk_lineups_${nextTs()}.json`, {
              lineups_requested: 20,
              lineups_generated: 20,
              stopped_reason: null,
              lineups: [],
            });
            return ok();
          },
        },
        calls,
      ),
    );

    const { buildLineups } = await import("../buildRunner");
    const result = await buildLineups(
      baseRequest({
        lineups: 20,
        objective: "leverage",
        locks: ["Paul Skenes"],
        exclusions: ["Some Player"],
        maxExposure: { "Kyle Schwarber": 0.5 },
        stackSize: 5,
        stackTeam: "PHI",
        allowPitcherVsHitter: true,
        minSalary: 45000,
        minUnique: 3,
        minConfidence: 60,
        maxPlayerRisk: 70,
      }),
    );

    expect(result.ok).toBe(true);
    const buildCall = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py" && !c.args.includes("--validate-only"))!;
    expect(argValue(buildCall.args, "--lineups")).toBe("20");
    expect(argValue(buildCall.args, "--objective")).toBe("leverage");
    expect(argValues(buildCall.args, "--lock")).toEqual(["Paul Skenes"]);
    expect(argValues(buildCall.args, "--exclude")).toEqual(["Some Player"]);
    expect(argValues(buildCall.args, "--max-exposure")).toEqual(["Kyle Schwarber=0.5"]);
    expect(argValue(buildCall.args, "--stack-size")).toBe("5");
    expect(argValue(buildCall.args, "--stack-team")).toBe("PHI");
    expect(buildCall.args).toContain("--allow-pitcher-vs-hitter");
    expect(argValue(buildCall.args, "--min-salary")).toBe("45000");
    expect(argValue(buildCall.args, "--min-unique")).toBe("3");
    expect(argValue(buildCall.args, "--min-confidence")).toBe("60");
    expect(argValue(buildCall.args, "--max-player-risk")).toBe("70");
    expect(buildCall.args).toContain("--interactive");
  });

  it("skips the real solve entirely when the pre-check finds errors", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: ["some contradiction"] })) }, calls),
    );

    const { buildLineups } = await import("../buildRunner");
    const result = await buildLineups(baseRequest());
    expect(result.ok).toBe(false);
    expect(result.errors).toEqual(["some contradiction"]);
    // Exactly one optimize_dk_lineups.py invocation -- the validate-only
    // pre-check -- never a second (real, slow) solve attempt.
    expect(calls.filter((c) => c.script === "scripts/optimize_dk_lineups.py")).toHaveLength(1);
  });

  it("extracts a CONFIGURATION ERROR message when the real build unexpectedly fails after passing pre-check", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/optimize_dk_lineups.py": (args) => {
            if (args.includes("--validate-only")) return ok(JSON.stringify({ errors: [] }));
            return ok("CONFIGURATION ERROR: --objective leverage requires --ownership (no player has a leverage_score).");
          },
        },
        calls,
      ),
    );

    const { buildLineups } = await import("../buildRunner");
    const result = await buildLineups(baseRequest({ objective: "leverage" }));
    expect(result.ok).toBe(false);
    expect(result.errors[0]).toMatch(/requires --ownership/);
  });

  it("returns the generated lineups and file paths on success", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/optimize_dk_lineups.py": (args) => {
            if (args.includes("--validate-only")) return ok(JSON.stringify({ errors: [] }));
            const ts = nextTs();
            const csvPath = path.join(tmpDir, "lineups", DATE, `dk_lineups_${ts}.csv`);
            fs.mkdirSync(path.dirname(csvPath), { recursive: true });
            fs.writeFileSync(csvPath, "Lineup,P1\n1,Ace Pitcher\n");
            writeJson(`lineups/${DATE}/dk_lineups_${ts}.json`, {
              lineups_requested: 1,
              lineups_generated: 1,
              stopped_reason: null,
              lineups: [{ index: 1, assignments: [], salary: 9000, projection: 20, ceiling: 30 }],
            });
            return ok();
          },
        },
        calls,
      ),
    );

    const { buildLineups } = await import("../buildRunner");
    const result = await buildLineups(baseRequest({ lineups: 1 }));
    expect(result.ok).toBe(true);
    expect(result.lineupsGenerated).toBe(1);
    expect(result.lineups).toHaveLength(1);
    expect(result.lineupSetPath).toMatch(/dk_lineups_.*\.json$/);
    expect(result.csvPath).toMatch(/dk_lineups_.*\.csv$/);
    expect(result.elapsedMs).toBeGreaterThanOrEqual(0);
  });

  it("fails cleanly when no pool has been loaded", async () => {
    const { buildLineups } = await import("../buildRunner");
    const result = await buildLineups(baseRequest());
    expect(result.ok).toBe(false);
    expect(result.errors[0]).toMatch(/select a slate first/i);
  });

  it("never sends --max-exposure for a player left at the 100% default", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    await seedCachedPool(calls);
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/optimize_dk_lineups.py": (args) => {
            if (args.includes("--validate-only")) return ok(JSON.stringify({ errors: [] }));
            writeJson(`lineups/${DATE}/dk_lineups_${nextTs()}.json`, { lineups_requested: 1, lineups_generated: 1, stopped_reason: null, lineups: [] });
            return ok();
          },
        },
        calls,
      ),
    );

    const { buildLineups } = await import("../buildRunner");
    await buildLineups(baseRequest({ lineups: 1, maxExposure: { "Full Exposure Guy": 1 } }));
    const buildCall = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py" && !c.args.includes("--validate-only"))!;
    expect(buildCall.args).not.toContain("--max-exposure");
  });
});
