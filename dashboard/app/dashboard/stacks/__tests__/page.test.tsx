import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

// Milestone 29: resolveSlateContext() filters slates to PUBLISHED-only
// for a non-admin viewer -- this file's fixtures predate that filter,
// so pass every slate through unchanged (as an ADMIN viewer would see it).
vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: async (slates: unknown) => slates,
}));

import StacksPage from "../page";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let originalRoot: string | undefined;

beforeEach(async () => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-stacks-page-test";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse({ run: null })),
  );
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

describe("StacksPage (missing batter snapshot)", () => {
  it("shows Refresh Required Data instead of a developer command", async () => {
    const jsx = await StacksPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Refresh Required Data")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
  });
});

describe("StacksPage -- Milestone 32.6 Part 4: Use This Stack handoff", () => {
  const DATE = "2026-08-17";
  let tmpDir: string;

  function writeJson(relPath: string, data: unknown) {
    const filePath = path.join(tmpDir, relPath);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(data));
  }

  function hitter(overrides: Record<string, unknown> = {}) {
    return {
      player_id: "h1", name: "Confirmed One", team: "BOS", opponent: "NYY", game_id: "g1",
      batting_order: 1, projection: 10, ceiling: 18, overall_score: 60, risk_score: 30, confidence: 80,
      tags: [], reasons: [], ...overrides,
    };
  }

  function poolPlayer(overrides: Record<string, unknown> = {}) {
    return {
      dk_player_id: "d1", mlb_player_id: "h1", name: "Confirmed One", team: "BOS", player_type: "hitter",
      dk_positions: ["OF"], salary: 4000, opponent: "NYY", game_id: "g1", batting_order: 1,
      projection: 10, ceiling: 18, floor: 4, overall_score: 60, risk_score: 30, confidence: 80,
      tags: [], reasons: [], lineup_status: "active", match_status: "matched",
      eligibility_status: "STARTING_HITTER", optimizer_eligible: true, ...overrides,
    };
  }

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-stacks-handoff-"));
    process.env.MLB_DFS_ROOT = tmpDir;
    vi.doMock("@/lib/currentDate", () => ({ getTodayChicagoDate: () => DATE }));
    vi.resetModules();
  });

  afterEach(() => {
    vi.doUnmock("@/lib/currentDate");
    vi.resetModules();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('shows "Use This Stack" only for a CONFIRMED team with 2+ confirmed hitters, linking to the Optimizer with the team stack rule', async () => {
    writeJson(`predictions/${DATE}/batter_board_20260817T180000.json`, {
      slate_date: DATE, generated_at: `${DATE}T18:00:00Z`, model_version: "0.6.0", hitter_count: 2, missing_lineup_game_ids: [],
      hitters: [hitter(), hitter({ player_id: "h2", name: "Confirmed Two", batting_order: 2 })],
    });
    writeJson(`dfs_input/${DATE}/dk_player_pool_20260817T180000.json`, {
      slate_date: DATE, generated_at_utc: `${DATE}T18:00:00Z`, pitcher_snapshot_path: null, batter_snapshot_path: null,
      player_count: 2, selected_slate_id: null,
      players: [poolPlayer(), poolPlayer({ dk_player_id: "d2", mlb_player_id: "h2", name: "Confirmed Two", batting_order: 2 })],
    });

    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "not_connected", reason: null, provider_name: null, provider_type: null,
        is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
      }),
      stderr: "", command: [],
    }));

    const StacksPageFresh = (await import("../page")).default;
    const jsx = await StacksPageFresh({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    const link = screen.getByRole("link", { name: /Use This Stack/i });
    expect(link).toHaveAttribute("href", "/dashboard/optimizer?stackTeam=BOS&stackSize=2");
  });

  it("never offers Use This Stack while a team is still WAITING_FOR_LINEUP", async () => {
    writeJson(`predictions/${DATE}/batter_board_20260817T180000.json`, {
      slate_date: DATE, generated_at: `${DATE}T18:00:00Z`, model_version: "0.6.0", hitter_count: 1, missing_lineup_game_ids: [],
      hitters: [hitter({ batting_order: null })],
    });
    writeJson(`dfs_input/${DATE}/dk_player_pool_20260817T180000.json`, {
      slate_date: DATE, generated_at_utc: `${DATE}T18:00:00Z`, pitcher_snapshot_path: null, batter_snapshot_path: null,
      player_count: 1, selected_slate_id: null,
      players: [poolPlayer({ optimizer_eligible: false, lineup_status: "bench", eligibility_status: "UNCONFIRMED" })],
    });

    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "not_connected", reason: null, provider_name: null, provider_type: null,
        is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
      }),
      stderr: "", command: [],
    }));

    const StacksPageFresh = (await import("../page")).default;
    const jsx = await StacksPageFresh({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Waiting For Lineup")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Use This Stack/i })).not.toBeInTheDocument();
  });

  it("preserves the currently-selected slate in the Use This Stack link", async () => {
    writeJson(`predictions/${DATE}/batter_board_20260817T180000.json`, {
      slate_date: DATE, generated_at: `${DATE}T18:00:00Z`, model_version: "0.6.0", hitter_count: 2, missing_lineup_game_ids: [],
      hitters: [hitter(), hitter({ player_id: "h2", name: "Confirmed Two", batting_order: 2 })],
    });
    writeJson(`dfs_input/${DATE}/dk_player_pool_20260817T180000.json`, {
      slate_date: DATE, generated_at_utc: `${DATE}T18:00:00Z`, pitcher_snapshot_path: null, batter_snapshot_path: null,
      player_count: 2, selected_slate_id: "dkunofficial-152547",
      players: [poolPlayer(), poolPlayer({ dk_player_id: "d2", mlb_player_id: "h2", name: "Confirmed Two", batting_order: 2 })],
    });

    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script: string) => {
      if (script === "scripts/list_dfs_slates.py") {
        return {
          exitCode: 0,
          stdout: JSON.stringify({
            status: "ready", reason: null, provider_name: "draftkings_unofficial", provider_type: "real",
            is_mock: false, is_connected: true, source: "explicit",
            slates: [{ slate_id: "dkunofficial-152547", slate_name: "Featured", game_count: 1, start_time: null, game_ids: ["g1"], player_count: 2 }],
            slates_available: 1,
          }),
          stderr: "", command: [],
        };
      }
      throw new Error(`Unexpected script call: ${script}`);
    });

    const StacksPageFresh = (await import("../page")).default;
    const jsx = await StacksPageFresh({ searchParams: Promise.resolve({ slate: "dkunofficial-152547" }) } as never);
    render(jsx);

    const link = screen.getByRole("link", { name: /Use This Stack/i });
    expect(link).toHaveAttribute("href", "/dashboard/optimizer?slate=dkunofficial-152547&stackTeam=BOS&stackSize=2");
  });
});
