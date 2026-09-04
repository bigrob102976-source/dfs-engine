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

const NO_SLATES = ok(
  JSON.stringify({
    status: "not_connected", reason: null, provider_name: null, provider_type: null,
    is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
  }),
);

// Milestone 32.6: EnvironmentPage now also calls resolveSlateContext(),
// which shells out to scripts/list_dfs_slates.py -- stub it so the test
// never spawns a real Python subprocess.
function makeSlateRunner(slatesResult: PythonRunResult = NO_SLATES): PythonRunner {
  return async (script) => {
    if (script === "scripts/list_dfs_slates.py") return slatesResult;
    throw new Error(`Unexpected script call in test: ${script}`);
  };
}

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-environment-page-test";
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  vi.restoreAllMocks();
});

describe("EnvironmentPage (no snapshot yet)", () => {
  it("shows a friendly empty state with a Generate action, never a raw script command", async () => {
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeSlateRunner());

    const EnvironmentPage = (await import("../page")).default;
    const jsx = await EnvironmentPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("No Game Environment report yet for today's slate")).toBeInTheDocument();
    expect(screen.getByText("Generate Environment Report")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });
});

describe("EnvironmentPage (slate filtering -- Milestone 32.6)", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-environment-page-"));
    process.env.MLB_DFS_ROOT = tmpDir;
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function writeSnapshot() {
    const dir = path.join(tmpDir, "game_environment_snapshots", "2026-08-13");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "environment_20260813T180000.json"),
      JSON.stringify({
        slate_date: "2026-08-13",
        generated_at: "2026-08-13T18:00:00Z",
        engine_version: "0.1.0",
        games: [
          buildGameEnvironmentReport({ game_id: "824238", home_team: "DET", away_team: "CLE" }),
          buildGameEnvironmentReport({ game_id: "999111", home_team: "LAD", away_team: "SFG" }),
        ],
        vegas_slate_analysis: null,
        warnings: [],
      }),
    );
  }

  it("shows every game for Full Day (no slate selected)", async () => {
    writeSnapshot();
    vi.doMock("@/lib/currentDate", () => ({ getTodayEasternDate: () => "2026-08-13" }));
    vi.resetModules();
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeSlateRunner());

    const EnvironmentPage = (await import("../page")).default;
    const jsx = await EnvironmentPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
    expect(screen.getByText("SFG @ LAD")).toBeInTheDocument();
    vi.doUnmock("@/lib/currentDate");
    vi.resetModules();
  });

  it("shows only the selected slate's games -- a Night slate never leaks a Main-only game", async () => {
    writeSnapshot();
    vi.doMock("@/lib/currentDate", () => ({ getTodayEasternDate: () => "2026-08-13" }));
    vi.resetModules();
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeSlateRunner(
        ok(
          JSON.stringify({
            status: "ready", reason: null, provider_name: "DRAFTKINGS_UNOFFICIAL_LIVE", provider_type: "real",
            is_mock: false, is_connected: true, source: "live",
            slates: [{ slate_id: "night", slate_name: "Night", game_count: 1, start_time: null, game_ids: ["824238"], player_count: 50 }],
            slates_available: 1,
          }),
        ),
      ),
    );

    const EnvironmentPage = (await import("../page")).default;
    const jsx = await EnvironmentPage({ searchParams: Promise.resolve({ slate: "night" }) } as never);
    render(jsx);

    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
    expect(screen.queryByText("SFG @ LAD")).not.toBeInTheDocument();
    vi.doUnmock("@/lib/currentDate");
    vi.resetModules();
  });
});
