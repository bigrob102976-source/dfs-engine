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
    projectionSource: "independent",
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

  describe("Milestone 17: projectionSource -> --projection-overrides", () => {
    function seedAdjustedSnapshot() {
      writeJson(`adjusted_projection_snapshots/${DATE}/adjusted_20260812T200000.json`, {
        slate_date: DATE,
        generated_at: "2026-08-12T20:00:00Z",
        records: [
          {
            independent_player_id: "h1", name: "Kyle Schwarber", team: "PHI", player_type: "hitter",
            external_projection: 11.2, adjusted_projection: 12.1, adjustment_delta: 0.9, adjustment_percent: 8.0,
            adjustment_confidence: 85, adjustment_reasons: ["positive recent hard-hit trend"], adjustments: [],
          },
        ],
      });
    }

    it("independent (the default) never passes --projection-overrides -- byte-identical to pre-M17 behavior", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      seedAdjustedSnapshot();
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: [] })) }, calls),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "independent" }));
      const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
      expect(call.args).not.toContain("--projection-overrides");
    });

    it("external/adjusted write a --projection-overrides file with the chosen source's values", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      seedAdjustedSnapshot();
      let capturedOverrides: Record<string, { projection: number }> | null = null;
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner(
          {
            "scripts/optimize_dk_lineups.py": (args) => {
              // Must read the overrides file WHILE the script is "running" --
              // buildRunner.ts deletes it immediately after this call returns.
              const overridesPath = argValue(args, "--projection-overrides");
              if (overridesPath) capturedOverrides = JSON.parse(fs.readFileSync(overridesPath, "utf-8"));
              return ok(JSON.stringify({ errors: [] }));
            },
          },
          calls,
        ),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "adjusted" }));

      const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
      expect(argValue(call.args, "--projection-overrides")).toBeTruthy();
      expect(capturedOverrides).not.toBeNull();
      expect(capturedOverrides!.h1.projection).toBe(12.1);
    });

    it("external source uses external_projection, not adjusted_projection", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      seedAdjustedSnapshot();
      let capturedOverrides: Record<string, { projection: number }> | null = null;
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner(
          {
            "scripts/optimize_dk_lineups.py": (args) => {
              const overridesPath = argValue(args, "--projection-overrides");
              if (overridesPath) capturedOverrides = JSON.parse(fs.readFileSync(overridesPath, "utf-8"));
              return ok(JSON.stringify({ errors: [] }));
            },
          },
          calls,
        ),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "external" }));

      expect(capturedOverrides).not.toBeNull();
      expect(capturedOverrides!.h1.projection).toBe(11.2);
    });

    it("cleans up the temp overrides file after the run", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      seedAdjustedSnapshot();
      let overridesPath: string | undefined;
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner(
          {
            "scripts/optimize_dk_lineups.py": (args) => {
              overridesPath = argValue(args, "--projection-overrides");
              return ok(JSON.stringify({ errors: [] }));
            },
          },
          calls,
        ),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "adjusted" }));

      expect(overridesPath).toBeTruthy();
      expect(fs.existsSync(overridesPath!)).toBe(false);
    });

    it("adjusted/external with no adjusted snapshot at all never passes --projection-overrides (graceful fallback)", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      // Deliberately no seedAdjustedSnapshot() here.
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: [] })) }, calls),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      const errors = await validateBuildRequest(baseRequest({ projectionSource: "adjusted" }));
      expect(errors).toEqual([]);
      const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
      expect(call.args).not.toContain("--projection-overrides");
    });

    it("native (Milestone 23) writes a --projection-overrides file with native projection/ceiling/floor", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      writeJson(`native_projection_snapshots/${DATE}/native_projection_20260812T200000.json`, {
        slate_date: DATE, generated_at: `${DATE}T20:00:00Z`, model_version: "1.0.0",
        pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
        player_count: 1,
        players: [
          { player_id: "h1", name: "Kyle Schwarber", team: "PHI", player_type: "hitter", native_projection: 9.6, native_ceiling: 16.2, native_floor: 3.5, confidence: 75, reasons: [] },
        ],
        warnings: [],
      });
      let capturedOverrides: Record<string, { projection: number; ceiling: number; floor: number }> | null = null;
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner(
          {
            "scripts/optimize_dk_lineups.py": (args) => {
              const overridesPath = argValue(args, "--projection-overrides");
              if (overridesPath) capturedOverrides = JSON.parse(fs.readFileSync(overridesPath, "utf-8"));
              return ok(JSON.stringify({ errors: [] }));
            },
          },
          calls,
        ),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "native" }));

      expect(capturedOverrides).not.toBeNull();
      expect(capturedOverrides!.h1.projection).toBe(9.6);
      expect(capturedOverrides!.h1.ceiling).toBe(16.2);
      expect(capturedOverrides!.h1.floor).toBe(3.5);
    });

    it("native with no native snapshot at all never passes --projection-overrides (graceful fallback)", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      // Deliberately no native snapshot written.
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: [] })) }, calls),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      const errors = await validateBuildRequest(baseRequest({ projectionSource: "native" }));
      expect(errors).toEqual([]);
      const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
      expect(call.args).not.toContain("--projection-overrides");
    });

    it("fantasypros writes a --projection-overrides file with dk_points as the projection, leaving ceiling/floor null", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260812T200000.json`, {
        slate_date: DATE, retrieved_at: `${DATE}T20:00:00Z`, hitter_count: 1, pitcher_count: 0,
        hitters_matched: 1, pitchers_matched: 0, public_api_limited: true, api_tier: "free",
        players: [
          {
            fantasypros_id: "1", name: "Kyle Schwarber", team: "PHI", player_type: "hitter", yahoo_id: null,
            raw_stats: {}, dk_points: 8.4, dk_points_breakdown: {}, match_status: "matched",
            match_confidence: "name_team_exact", mlb_player_id: "h1", candidate_mlb_ids: [], candidate_names: [],
          },
        ],
      });
      let capturedOverrides: Record<string, { projection: number; ceiling: number | null; floor: number | null }> | null = null;
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner(
          {
            "scripts/optimize_dk_lineups.py": (args) => {
              const overridesPath = argValue(args, "--projection-overrides");
              if (overridesPath) capturedOverrides = JSON.parse(fs.readFileSync(overridesPath, "utf-8"));
              return ok(JSON.stringify({ errors: [] }));
            },
          },
          calls,
        ),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      await validateBuildRequest(baseRequest({ projectionSource: "fantasypros" }));

      expect(capturedOverrides).not.toBeNull();
      expect(capturedOverrides!.h1.projection).toBe(8.4);
      expect(capturedOverrides!.h1.ceiling).toBeNull();
      expect(capturedOverrides!.h1.floor).toBeNull();
    });

    it("fantasypros with no snapshot at all never passes --projection-overrides (graceful fallback)", async () => {
      const calls: Array<{ script: string; args: string[] }> = [];
      await seedCachedPool(calls);
      // Deliberately no FantasyPros snapshot written.
      const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
      __setPythonRunnerForTests(
        makeFakeRunner({ "scripts/optimize_dk_lineups.py": () => ok(JSON.stringify({ errors: [] })) }, calls),
      );
      const { validateBuildRequest } = await import("../buildRunner");
      const errors = await validateBuildRequest(baseRequest({ projectionSource: "fantasypros" }));
      expect(errors).toEqual([]);
      const call = calls.find((c) => c.script === "scripts/optimize_dk_lineups.py")!;
      expect(call.args).not.toContain("--projection-overrides");
    });
  });
});
