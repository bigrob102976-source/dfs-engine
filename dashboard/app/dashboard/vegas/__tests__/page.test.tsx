import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";
import type { PythonRunner, PythonRunResult } from "@/lib/orchestrator/pythonRunner";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

// Milestone 29: resolveSlateContext() filters slates to PUBLISHED-only
// for a non-admin viewer -- this file's fixtures predate that filter,
// so pass every slate through unchanged (as an ADMIN viewer would see it).
vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: async (slates: unknown) => slates,
}));

function ok(stdout: string): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}
function fail(): PythonRunResult {
  return { exitCode: 1, stdout: "", stderr: "boom", command: [] };
}

const STATUS_OK = JSON.stringify({
  slate_date: "2026-08-13",
  providers: {
    weather: { provider_name: "MOCK WEATHER", is_mock: true, source: "automatic_fallback" },
    vegas: { provider_name: "MOCK VEGAS", is_mock: true, source: "automatic_fallback" },
    umpire: { provider_name: "No umpire provider configured", is_mock: false, source: "unconfigured" },
    bullpen: { provider_name: "MOCK BULLPEN", is_mock: true, source: "automatic_fallback" },
  },
  report: { exists: false, generated_at: null, game_count: null, engine_version: null },
});

const NO_SLATES = ok(
  JSON.stringify({
    status: "not_connected", reason: null, provider_name: null, provider_type: null,
    is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
  }),
);

// Milestone 26: VegasPage now also calls resolveSlateContext(), which
// shells out to scripts/list_dfs_slates.py -- every test needs that
// stubbed too, not just the Game Environment status check.
function makeStatusRunner(result: PythonRunResult, slatesResult: PythonRunResult = NO_SLATES): PythonRunner {
  return async (script) => {
    if (script === "scripts/game_environment_status.py") return result;
    if (script === "scripts/list_dfs_slates.py") return slatesResult;
    throw new Error(`Unexpected script call in test: ${script}`);
  };
}

let tmpDir: string;
let originalRoot: string | undefined;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-vegas-page-"));
  originalRoot = process.env.MLB_DFS_ROOT;
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  fs.rmSync(tmpDir, { recursive: true, force: true });
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  vi.restoreAllMocks();
});

function writeSnapshot(date: string, doc: unknown) {
  const dir = path.join(tmpDir, "game_environment_snapshots", date);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "environment_20260813T180000.json"), JSON.stringify(doc));
}

describe("VegasPage", () => {
  it("shows 'No Games' with a Generate action when no snapshot exists yet, never a raw script path", async () => {
    process.env.MLB_DFS_ROOT = path.join(tmpDir, "nonexistent-nested-root");
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeStatusRunner(ok(STATUS_OK)));

    const VegasPage = (await import("../page")).default;
    const jsx = await VegasPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("No Games")).toBeInTheDocument();
    expect(screen.getByText("Generate Environment Report")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });

  it("shows 'Vegas Provider / NOT CONNECTED' when the report has games but none carry Vegas odds", async () => {
    process.env.MLB_DFS_ROOT = tmpDir;
    writeSnapshot("2026-08-13", {
      slate_date: "2026-08-13",
      generated_at: "2026-08-13T18:00:00Z",
      engine_version: "0.1.0",
      games: [buildGameEnvironmentReport({ vegas: null })],
      vegas_slate_analysis: null,
      warnings: [],
    });
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeStatusRunner(ok(STATUS_OK)));

    // getTodayEasternDate() must line up with the snapshot's folder date for
    // this fixture to be found; stub it via the module date helper instead
    // of relying on the real "today".
    vi.doMock("@/lib/currentDate", () => ({ getTodayEasternDate: () => "2026-08-13" }));
    vi.resetModules();
    const { __setPythonRunnerForTests: setRunnerAgain } = await import("@/lib/orchestrator/pythonRunner");
    setRunnerAgain(makeStatusRunner(ok(STATUS_OK)));

    const VegasPage = (await import("../page")).default;
    const jsx = await VegasPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Vegas Provider / NOT CONNECTED")).toBeInTheDocument();
    vi.doUnmock("@/lib/currentDate");
    vi.resetModules();
  });

  it("shows 'Provider Offline' when the status script fails unexpectedly", async () => {
    process.env.MLB_DFS_ROOT = path.join(tmpDir, "nonexistent-nested-root");
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeStatusRunner(fail()));

    const VegasPage = (await import("../page")).default;
    const jsx = await VegasPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Provider Offline")).toBeInTheDocument();
  });
});
