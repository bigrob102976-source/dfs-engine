import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

// Milestone 29: resolveSlateContext() filters slates to PUBLISHED-only
// for a non-admin viewer (lib/memberSlateVisibility.ts). This file's
// fixtures predate that filter and don't exercise it -- pass every
// slate through unchanged, as an ADMIN viewer would see it. (A real
// logged-in-admin session doesn't survive this file's later
// vi.resetModules() calls, which reload the DB module's singleton --
// mocking the filter directly sidesteps that entirely.)
vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: async (slates: unknown) => slates,
}));

import TopPitchersPage from "../page";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function writeJson(root: string, relPath: string, data: unknown) {
  const filePath = path.join(root, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

let originalRoot: string | undefined;

beforeEach(async () => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-pitchers-page-test";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse({ run: null })),
  );
  // Milestone 26: TopPitchersPage now calls resolveSlateContext(), which
  // shells out to scripts/list_dfs_slates.py -- stub the runner so this
  // test never spawns a real Python process.
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async () => ({
    exitCode: 0,
    stdout: JSON.stringify({
      status: "not_connected", reason: null, provider_name: null, provider_type: null,
      is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
    }),
    stderr: "",
    command: [],
  }));
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("TopPitchersPage (missing pitcher snapshot)", () => {
  it("shows Generate Pitcher Research instead of a developer command", async () => {
    const jsx = await TopPitchersPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Generate Pitcher Research")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/run_real_pitcher_agent/)).not.toBeInTheDocument();
  });
});

describe("TopPitchersPage (Milestone 26 slate filtering)", () => {
  const DATE = "2026-08-17";
  let tmpDir: string;

  beforeEach(async () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-pitchers-slate-"));
    process.env.MLB_DFS_ROOT = tmpDir;

    writeJson(tmpDir, `predictions/${DATE}/pitcher_board_20260817T180000.json`, {
      slate_date: DATE, generated_at: `${DATE}T18:00:00Z`, model_version: "0.6.0", pitcher_count: 2,
      pitchers: [
        { player_id: "p-main", name: "Main Ace", team: "BOS", opponent: "NYY", game_id: "g-main", projection: 20, ceiling: 30, overall_score: 80 },
        { player_id: "p-turbo", name: "Turbo Ace", team: "SD", opponent: "LAD", game_id: "g-turbo", projection: 18, ceiling: 28, overall_score: 75 },
      ],
    });

    vi.doMock("@/lib/currentDate", () => ({ getTodayChicagoDate: () => DATE }));
    vi.resetModules();
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script: string) => {
      if (script === "scripts/list_dfs_slates.py") {
        return {
          exitCode: 0,
          stdout: JSON.stringify({
            status: "ready", reason: null, provider_name: "draftkings_csv", provider_type: "real",
            is_mock: false, is_connected: true, source: "real_dk_csv",
            slates: [
              { slate_id: "main", slate_name: "Main", game_count: 1, start_time: null, game_ids: ["g-main"], player_count: 1 },
              { slate_id: "turbo", slate_name: "Turbo", game_count: 1, start_time: null, game_ids: ["g-turbo"], player_count: 1 },
            ],
            slates_available: 2,
          }),
          stderr: "",
          command: [],
        };
      }
      throw new Error(`Unexpected script call: ${script}`);
    });
  });

  afterEach(async () => {
    vi.doUnmock("@/lib/currentDate");
    vi.resetModules();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("shows every pitcher (Full Day) when no slate is selected", async () => {
    const TopPitchersPageFresh = (await import("../page")).default;
    const jsx = await TopPitchersPageFresh({ searchParams: Promise.resolve({}) } as never);
    render(jsx);
    expect(screen.getByText("Main Ace")).toBeInTheDocument();
    expect(screen.getByText("Turbo Ace")).toBeInTheDocument();
  });

  it("shows only Main's pitcher when Main is selected -- Turbo's pitcher never leaks in", async () => {
    const TopPitchersPageFresh = (await import("../page")).default;
    const jsx = await TopPitchersPageFresh({ searchParams: Promise.resolve({ slate: "main" }) } as never);
    render(jsx);
    expect(screen.getByText("Main Ace")).toBeInTheDocument();
    expect(screen.queryByText("Turbo Ace")).not.toBeInTheDocument();
  });

  it("shows only Turbo's pitcher when Turbo is selected -- Main's pitcher never leaks in", async () => {
    const TopPitchersPageFresh = (await import("../page")).default;
    const jsx = await TopPitchersPageFresh({ searchParams: Promise.resolve({ slate: "turbo" }) } as never);
    render(jsx);
    expect(screen.getByText("Turbo Ace")).toBeInTheDocument();
    expect(screen.queryByText("Main Ace")).not.toBeInTheDocument();
  });
});
