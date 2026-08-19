import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Milestone 26: OptimizerWorkspace reads `?slate=` via useSearchParams()
// to sync with the global slate selector -- an empty URL (no slate=)
// here matches every existing test's assumption that the Optimizer's
// own dropdown/localStorage-persisted selection is authoritative.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

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
      eligibilityStatus: "STARTING_HITTER",
      optimizerEligible: true,
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
      nativeProjection: null,
      nativeCeiling: null,
      nativeFloor: null,
      nativeDelta: null,
      nativeConfidence: null,
      nativeReasons: [],
      nativeExpectedPa: null,
      nativeExpectedInnings: null,
      nativeHitterComponents: null,
      nativePitcherComponents: null,
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
      eligibilityStatus: "STARTING_PITCHER",
      optimizerEligible: true,
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
      nativeProjection: null,
      nativeCeiling: null,
      nativeFloor: null,
      nativeDelta: null,
      nativeConfidence: null,
      nativeReasons: [],
      nativeExpectedPa: null,
      nativeExpectedInnings: null,
      nativeHitterComponents: null,
      nativePitcherComponents: null,
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
  vegasCoverage: { dkGames: 1, pregameCovered: 1, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 100, games: [] },
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

  it("Milestone 26: resets locks/exclusions on a real slate switch instead of reconciling by raw dkPlayerId, since DK ids collide across different slates' own exports (confirmed via live validation against real 2026-08-12 Main/Turbo CSVs, where id 1006 was Merrill Kelly in Main but Trevor Larnach in Turbo)", async () => {
    const TWO_SLATES = {
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
    };
    // Turbo's pool reuses "d1" for a completely different person -- exactly
    // the real DK-CSV-export collision live validation found.
    const TURBO_POOL = {
      ...POOL_RESULT,
      slateId: "turbo",
      slateName: "Turbo",
      players: [{ ...POOL_RESULT.players[0], dkPlayerId: "d1", name: "Different Turbo Player", team: "TB" }],
      activePlayers: 1,
    };
    let poolCallCount = 0;
    installFetchMock({
      "/api/optimizer/slates": () => jsonResponse(TWO_SLATES),
      "/api/optimizer/pool": () => {
        poolCallCount += 1;
        return jsonResponse({ pool: poolCallCount === 1 ? { ...POOL_RESULT, slateId: "main" } : TURBO_POOL });
      },
    });
    render(<OptimizerWorkspace />);
    await waitFor(() => expect(screen.getByText("Select a slate")).toBeInTheDocument(), { timeout: 5000 });

    fireEvent.change(screen.getByRole("combobox", { name: /Slate:/ }), { target: { value: "main" } });
    await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "Lock Leadoff Hitter" }));
    expect(screen.getByText("Locked (1)")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: /Slate:/ }), { target: { value: "turbo" } });
    await waitFor(() => expect(screen.getByText("Different Turbo Player")).toBeInTheDocument(), { timeout: 5000 });

    // The stale "d1" lock must NOT silently re-target the new pool's "d1"
    // (Different Turbo Player) -- it must be reset, not reconciled by id.
    expect(screen.queryByText("Locked (1)")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lock Different Turbo Player" })).toBeInTheDocument();
    expect(screen.getByText(/Switched slates.*Main.*Turbo.*reset/)).toBeInTheDocument();
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
      players: [
        { ...POOL_RESULT.players[0], lineupStatus: "lineup_not_confirmed", eligibilityStatus: "SCRATCHED", optimizerEligible: false },
        POOL_RESULT.players[1],
      ],
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
      externalProviderName: "BlueCollar DFS",
      players: [
        { ...POOL_RESULT.players[0], externalProjection: 9.2, adjustedProjection: 10.6, adjustmentDelta: 0.6, adjustmentPercent: 6.0, adjustmentReasons: ["positive recent hard-hit trend"] },
        { ...POOL_RESULT.players[1], externalProjection: 18.5, adjustedProjection: 20.3, adjustmentDelta: 0.3, adjustmentPercent: 1.5, adjustmentReasons: [] },
      ],
    };

    it("BlueCollar and BlueCollar (Adjusted) are disabled when the pool has no external projection data", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "BlueCollar" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "BlueCollar (Adjusted)" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Legacy" })).toBeEnabled();
      expect(screen.getByText(/BlueCollar not loaded/)).toBeInTheDocument();
    });

    it("falls back to Legacy when the slate has no native data (native is the default, but this fixture has none)", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Legacy" })).toHaveAttribute("aria-pressed", "true"),
      );
    });

    it("enables BlueCollar / BlueCollar (Adjusted) when the pool has comparison data, and switching sources is reflected in the build request", async () => {
      const { calls } = installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_COMPARISON }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "BlueCollar" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "BlueCollar (Adjusted)" })).toBeEnabled();
      expect(screen.queryByText(/BlueCollar not loaded/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "BlueCollar (Adjusted)" }));
      expect(screen.getByRole("button", { name: "BlueCollar (Adjusted)" })).toHaveAttribute("aria-pressed", "true");

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

      expect(screen.queryByRole("columnheader", { name: "BlueCollar" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByLabelText("Show comparison columns"));
      expect(screen.getByRole("columnheader", { name: "BlueCollar" })).toBeInTheDocument();
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

      expect(screen.getByRole("button", { name: "Big Money AI" })).toBeDisabled();
      expect(screen.getByText(/Big Money AI not generated yet/)).toBeInTheDocument();
    });

    it("enables AI Projection when the pool has AI data, and selecting it is reflected in the build request", async () => {
      const { calls } = installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "Big Money AI" })).toBeEnabled();
      fireEvent.click(screen.getByRole("button", { name: "Big Money AI" }));
      expect(screen.getByRole("button", { name: "Big Money AI" })).toHaveAttribute("aria-pressed", "true");

      await waitFor(() => {
        const validateCall = calls.filter((c) => c.url === "/api/optimizer/validate").at(-1);
        expect(validateCall).toBeDefined();
        const body = JSON.parse(validateCall!.init!.body as string);
        expect(body.projectionSource).toBe("ai");
      });
    });

    it("falls back to Legacy if the selected slate has no AI data", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      fireEvent.click(screen.getByRole("button", { name: "Big Money AI" }));
      expect(screen.getByRole("button", { name: "Big Money AI" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "Legacy" })).toHaveAttribute("aria-pressed", "false");
    });

    it("the player table always shows BM AI/AI Δ/AI Conf/AI Grade columns", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_AI }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("columnheader", { name: "BM AI" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Δ" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Conf" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "AI Grade" })).toBeInTheDocument();
    });
  });

  describe("Milestone 23: Native Projection selector", () => {
    const POOL_WITH_NATIVE = {
      ...POOL_RESULT,
      hasNativeProjections: true,
      players: [
        { ...POOL_RESULT.players[0], nativeProjection: 9.6, nativeCeiling: 15.3, nativeFloor: 3.9, nativeConfidence: 78 },
        { ...POOL_RESULT.players[1], nativeProjection: 21.2, nativeCeiling: 29.5, nativeFloor: 12.1, nativeConfidence: 85 },
      ],
    };

    it("Big Money Native is the default selection when the pool has native data (Milestone 23)", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_NATIVE }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      expect(screen.getByRole("button", { name: "Big Money Native" })).toHaveAttribute("aria-pressed", "true");
    });

    it("Big Money Native is disabled and shows a not-generated message when the pool has no native data", async () => {
      installFetchMock();
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "Big Money Native" })).toBeDisabled();
      expect(screen.getByText(/Big Money Native not generated yet/)).toBeInTheDocument();
    });

    it("enables Big Money Native when the pool has native data, and selecting it is reflected in the build request", async () => {
      const { calls } = installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_NATIVE }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });

      expect(screen.getByRole("button", { name: "Big Money Native" })).toBeEnabled();
      fireEvent.click(screen.getByRole("button", { name: "Big Money Native" }));
      expect(screen.getByRole("button", { name: "Big Money Native" })).toHaveAttribute("aria-pressed", "true");

      await waitFor(() => {
        const validateCall = calls.filter((c) => c.url === "/api/optimizer/validate").at(-1);
        expect(validateCall).toBeDefined();
        const body = JSON.parse(validateCall!.init!.body as string);
        expect(body.projectionSource).toBe("native");
      });
    });

    it("falls back to Legacy if the selected slate has no native data", async () => {
      installFetchMock({ "/api/optimizer/pool": () => jsonResponse({ pool: POOL_WITH_NATIVE }) });
      render(<OptimizerWorkspace />);
      await waitFor(() => expect(screen.getByText("Leadoff Hitter")).toBeInTheDocument(), { timeout: 5000 });
      fireEvent.click(screen.getByRole("button", { name: "Big Money Native" }));
      expect(screen.getByRole("button", { name: "Big Money Native" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "Legacy" })).toHaveAttribute("aria-pressed", "false");
    });
  });
});
