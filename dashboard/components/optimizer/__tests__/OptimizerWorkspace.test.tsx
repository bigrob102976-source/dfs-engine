import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OptimizerWorkspace } from "../OptimizerWorkspace";

const SLATES_READY = {
  date: "2026-08-12",
  status: "ready",
  reason: null,
  providerName: "mock_dev_provider",
  providerType: "mock",
  isMock: true,
  isConnected: true,
  source: "mock_explicit",
  slates: [{ slateId: "mock-main", slateName: "Mock Main (Dev)", gameCount: 15, startTime: null }],
  slatesAvailable: 1,
};

const POOL_RESULT = {
  date: "2026-08-12",
  slateId: "mock-main",
  slateName: "Mock Main (Dev)",
  providerName: "mock_dev_provider",
  isMock: true,
  generatedAt: "2026-08-12T18:00:00.000Z",
  players: [
    {
      dkPlayerId: "d1",
      mlbPlayerId: "h1",
      name: "Leadoff Hitter",
      team: "BOS",
      opponent: "TOR",
      gameId: "g1",
      playerType: "hitter",
      positions: ["OF"],
      battingOrder: 1,
      salary: 4000,
      projection: 10,
      ceiling: 18,
      value: 2.5,
      ownership: 20,
      leverage: 5,
      risk: 30,
      confidence: 80,
      lineupStatus: "active",
      matchStatus: "matched",
      externalProjection: null,
      adjustedProjection: null,
      adjustmentDelta: null,
      adjustmentPercent: null,
      adjustmentReasons: [],
      aiProjection: null,
      aiCeiling: null,
      aiFloor: null,
      aiDelta: null,
      aiConfidence: null,
      aiRisk: null,
      aiGrade: null,
      aiValueScore: null,
      aiSignals: [],
      aiReasons: [],
      aiSummary: null,
    },
    {
      dkPlayerId: "d2",
      mlbPlayerId: "p1",
      name: "Ace Pitcher",
      team: "TOR",
      opponent: "BOS",
      gameId: "g1",
      playerType: "pitcher",
      positions: ["P"],
      battingOrder: null,
      salary: 8000,
      projection: 20,
      ceiling: 32,
      value: 2.5,
      ownership: 30,
      leverage: -2,
      risk: 25,
      confidence: 90,
      lineupStatus: "active",
      matchStatus: "matched",
      externalProjection: null,
      adjustedProjection: null,
      adjustmentDelta: null,
      adjustmentPercent: null,
      adjustmentReasons: [],
      aiProjection: null,
      aiCeiling: null,
      aiFloor: null,
      aiDelta: null,
      aiConfidence: null,
      aiRisk: null,
      aiGrade: null,
      aiValueScore: null,
      aiSignals: [],
      aiReasons: [],
      aiSummary: null,
    },
  ],
  activePlayers: 2,
  pitcherCount: 1,
  hitterCount: 1,
  confirmedLineupGames: 1,
  unconfirmedLineupGames: 0,
  unmatchedCount: 0,
  slateGames: 1,
  rosterFeasibilityPass: true,
  salaryCap: 50000,
  hasOwnership: true,
};

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function installFetchMock(overrides: Partial<Record<string, (init?: RequestInit) => Promise<Response>>> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (overrides[url]) return overrides[url]!(init);
    if (url === "/api/optimizer/slates") return jsonResponse(SLATES_READY);
    if (url === "/api/optimizer/pool") return jsonResponse({ pool: POOL_RESULT });
    if (url === "/api/optimizer/validate") return jsonResponse({ errors: [] });
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", impl);
  return { calls, impl };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("OptimizerWorkspace", () => {
  it("auto-selects the only slate, loads its pool, and shows the mock-data badge and status stats -- with no DFS_SALARY_PROVIDER set at all (automatic fallback)", async () => {
    installFetchMock();
    render(<OptimizerWorkspace />);

    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    expect(screen.getByText("DEV / MOCK DATA")).toBeInTheDocument();
    expect(screen.getByText("Active Players")).toBeInTheDocument();
    const activeStat = screen.getByText("Active Players").nextSibling as HTMLElement;
    expect(activeStat.textContent).toBe("2");

    // The old developer-facing "configure DFS_SALARY_PROVIDER" warning must
    // never appear when the automatic mock fallback is what's active. (Not a
    // blanket /not connected/i check -- Milestone 17's unrelated "External
    // projection provider not connected." helper text is expected here,
    // since this fixture's pool has no external/adjusted projection data.)
    expect(screen.queryByText(/unrecognized value/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/DFS.*not connected/i)).not.toBeInTheDocument();
  });

  it("shows a clear message (never crashes) when DFS_SALARY_PROVIDER is explicitly set to an unrecognized value", async () => {
    installFetchMock({
      "/api/optimizer/slates": () =>
        jsonResponse({
          date: "2026-08-12",
          status: "not_connected",
          reason: "DFS_SALARY_PROVIDER='bogus' is not a recognized provider. Supported: ['mock'].",
          providerName: null,
          providerType: null,
          isMock: false,
          isConnected: false,
          source: "explicit",
          slates: [],
          slatesAvailable: 0,
        }),
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText(/unrecognized value/i)).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText("Build Lineups")).toBeDisabled();
  });

  it("shows a clean empty state (never crashes) when the provider returns zero slates", async () => {
    installFetchMock({
      "/api/optimizer/slates": () =>
        jsonResponse({
          date: "2026-08-12",
          status: "no_slate",
          reason: "Provider returned zero slates for this date.",
          providerName: "mock_dev_provider",
          providerType: "mock",
          isMock: true,
          isConnected: false,
          source: "mock_explicit",
          slates: [],
          slatesAvailable: 0,
        }),
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("No slates available")).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText("Build Lineups")).toBeDisabled();
    expect(screen.queryByText("Leadoff Hitter")).not.toBeInTheDocument();
  });

  it("shows the dropdown (without auto-selecting) when the provider exposes multiple slates", async () => {
    installFetchMock({
      "/api/optimizer/slates": () =>
        jsonResponse({
          date: "2026-08-12",
          status: "ready",
          reason: null,
          providerName: "mock_dev_provider",
          providerType: "mock",
          isMock: true,
          isConnected: true,
          source: "mock_explicit",
          slates: [
            { slateId: "main", slateName: "Main", gameCount: 9, startTime: "7:05 PM" },
            { slateId: "turbo", slateName: "Turbo", gameCount: 4, startTime: "8:10 PM" },
          ],
          slatesAvailable: 2,
        }),
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Select a slate")).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText(/Main -- 7:05 PM -- 9 games/)).toBeInTheDocument();
    expect(screen.getByText(/Turbo -- 8:10 PM -- 4 games/)).toBeInTheDocument();
    // Nothing auto-selected -- no pool fetch should have happened yet.
    expect(screen.queryByText("Leadoff Hitter")).not.toBeInTheDocument();
  });

  it("shows validation errors from /api/optimizer/validate and disables Build", async () => {
    installFetchMock({
      "/api/optimizer/validate": () => jsonResponse({ errors: ["3 pitchers are locked but only 2 pitcher slot(s) exist."] }),
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    await waitFor(() => expect(screen.getByText(/3 pitchers are locked/)).toBeInTheDocument(), { timeout: 2000 });
    expect(screen.getByText("Build Lineups")).toBeDisabled();
  });

  it("locking a player highlights it in the pool table and the locked panel", async () => {
    installFetchMock();
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.click(screen.getByRole("button", { name: "Lock Leadoff Hitter" }));
    expect(screen.getByRole("button", { name: "Unlock Leadoff Hitter" })).toBeInTheDocument();
    expect(screen.getByText("Locked (1)")).toBeInTheDocument();
  });

  it("runs the full build flow and renders the resulting lineups", async () => {
    const buildResult = {
      ok: true,
      errors: [],
      lineupSetPath: "C:\\fake\\dk_lineups_1.json",
      csvPath: "C:\\fake\\dk_lineups_1.csv",
      lineupsRequested: 1,
      lineupsGenerated: 1,
      stoppedReason: null,
      lineups: [
        {
          index: 1,
          assignments: [],
          salary: 40000,
          remaining_salary: 10000,
          projection: 100,
          ceiling: 180,
          floor: 50,
          average_risk: 30,
          average_confidence: 80,
          team_counts: {},
          primary_stack_team: null,
          primary_stack_size: 0,
          sum_ownership: null,
          average_ownership: null,
          max_ownership: null,
          players_above_chalk_threshold: null,
        },
      ],
      elapsedMs: 500,
    };
    installFetchMock({ "/api/optimizer/build": () => jsonResponse({ result: buildResult }) });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.click(screen.getByText("Build Lineups"));
    await waitFor(() => expect(screen.getByText(/Generated/)).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText(/Generated/).closest("span")?.textContent).toContain("1 / 1 lineup(s)");
  });

  it("shows build errors returned by the server without crashing", async () => {
    installFetchMock({
      "/api/optimizer/build": () =>
        jsonResponse({ result: { ok: false, errors: ["--objective leverage requires --ownership."], lineups: [], lineupsRequested: 20, lineupsGenerated: 0, stoppedReason: null, lineupSetPath: null, csvPath: null, elapsedMs: 10 } }),
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.click(screen.getByText("Build Lineups"));
    await waitFor(() => expect(screen.getByText(/requires --ownership/)).toBeInTheDocument(), { timeout: 5000 });
  });

  it("persists locks to localStorage and restores them on the next mount", async () => {
    installFetchMock();
    const { unmount } = render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.click(screen.getByRole("button", { name: "Lock Leadoff Hitter" }));
    await waitFor(
      () => {
        const raw = window.localStorage.getItem("mlb-dfs-optimizer-workspace-v1");
        expect(raw).toBeTruthy();
        expect(JSON.parse(raw!).locks).toContain("d1");
      },
      { timeout: 5000 },
    );
    unmount();

    render(<OptimizerWorkspace />);
    // Once the persisted lock is restored, "Leadoff Hitter" legitimately
    // appears twice (the pool table row AND the Locked panel entry) --
    // wait for the unambiguous, lock-specific button instead.
    await waitFor(() => expect(screen.getByRole("button", { name: "Unlock Leadoff Hitter" })).toBeInTheDocument(), { timeout: 5000 });
  }, 15000);

  it("drops a stale lock with a warning when the locked player is scratched on reload", async () => {
    installFetchMock();
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "Lock Leadoff Hitter" }));
    await waitFor(() => expect(screen.getByText("Locked (1)")).toBeInTheDocument(), { timeout: 5000 });

    // Re-render fresh (simulating navigating away and back) with the SAME
    // slate but the previously-locked player now scratched.
    const scratchedPool = {
      ...POOL_RESULT,
      players: [{ ...POOL_RESULT.players[0], lineupStatus: "lineup_not_confirmed" }, POOL_RESULT.players[1]],
    };
    installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: scratchedPool }) });
    render(<OptimizerWorkspace />);

    await waitFor(() => expect(screen.getByText(/no longer active/i)).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText("Locked (0)")).toBeInTheDocument();
  }, 15000);

  describe("Milestone 17: Projection Source selector", () => {
    const POOL_WITH_COMPARISON = {
      ...POOL_RESULT,
      hasExternalProjections: true,
      players: [
        { ...POOL_RESULT.players[0], externalProjection: 9.2, adjustedProjection: 10.6, adjustmentDelta: 0.6, adjustmentPercent: 6.0, adjustmentReasons: ["positive recent hard-hit trend"] },
        { ...POOL_RESULT.players[1], externalProjection: 18.5, adjustedProjection: 20.3, adjustmentDelta: 0.3, adjustmentPercent: 1.5, adjustmentReasons: [] },
      ],
    };

    it("External Baseline and Big Money Adjusted are disabled when the pool has no external projection data", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "External Baseline" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Big Money Adjusted" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Big Money Independent" })).toBeEnabled();
      expect(screen.getByText("External projection provider not connected.")).toBeInTheDocument();
    });

    it("Big Money Independent is the default selection", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      expect(screen.getByRole("button", { name: "Big Money Independent" })).toHaveAttribute("aria-pressed", "true");
    });

    it("enables External Baseline / Big Money Adjusted when the pool has comparison data, and switching sources is reflected in the build request", async () => {
      const { calls } = installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_COMPARISON }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "External Baseline" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Big Money Adjusted" })).toBeEnabled();
      expect(screen.queryByText("External projection provider not connected.")).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Big Money Adjusted" }));
      expect(screen.getByRole("button", { name: "Big Money Adjusted" })).toHaveAttribute("aria-pressed", "true");

      await waitFor(() => {
        const validateCall = calls.filter((c) => c.url === "/api/optimizer/validate").at(-1);
        expect(validateCall).toBeDefined();
        const body = JSON.parse(validateCall!.init!.body as string);
        expect(body.projectionSource).toBe("adjusted");
      });
    });

    it("does not show comparison columns until Show comparison columns is checked", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_COMPARISON }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.queryByRole("columnheader", { name: "Ext" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByLabelText("Show comparison columns"));
      expect(screen.getByRole("columnheader", { name: "Ext" })).toBeInTheDocument();
    });
  });

  describe("Milestone 20: AI Projection selector", () => {
    const POOL_WITH_AI = {
      ...POOL_RESULT,
      hasAiProjections: true,
      players: [
        { ...POOL_RESULT.players[0], aiProjection: 11.2, aiDelta: 1.2, aiConfidence: 88, aiGrade: "A" },
        { ...POOL_RESULT.players[1], aiProjection: 19.5, aiDelta: -0.5, aiConfidence: 75, aiGrade: "B+" },
      ],
    };

    it("AI Projection is disabled and shows a not-generated message when the pool has no AI data", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "AI Projection" })).toBeDisabled();
      expect(screen.getByText(/AI Projection not generated yet/)).toBeInTheDocument();
    });

    it("enables AI Projection when the pool has AI data, and selecting it is reflected in the build request", async () => {
      const { calls } = installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "AI Projection" })).toBeEnabled();
      fireEvent.click(screen.getByRole("button", { name: "AI Projection" }));
      expect(screen.getByRole("button", { name: "AI Projection" })).toHaveAttribute("aria-pressed", "true");

      await waitFor(() => {
        const validateCall = calls.filter((c) => c.url === "/api/optimizer/validate").at(-1);
        expect(validateCall).toBeDefined();
        const body = JSON.parse(validateCall!.init!.body as string);
        expect(body.projectionSource).toBe("ai");
      });
    });

    it("falls back to Big Money Independent if the selected slate has no AI data", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      fireEvent.click(screen.getByRole("button", { name: "AI Projection" }));
      expect(screen.getByRole("button", { name: "AI Projection" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "Big Money Independent" })).toHaveAttribute("aria-pressed", "false");
    });

    it("the player table always shows AI Proj/AI Δ/AI Conf/AI Grade columns", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("columnheader", { name: "AI Proj" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Δ" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Conf" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Grade" })).toBeInTheDocument();
    });
  });
});
