import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConstraintsPanel } from "../ConstraintsPanel";
import type { OptimizerPoolResult, PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

function player(overrides: Partial<PoolPlayerRow>): PoolPlayerRow {
  return {
    dkPlayerId: "d1",
    mlbPlayerId: "h1",
    name: "Player",
    team: "AAA",
    opponent: "BBB",
    gameId: "g1",
    playerType: "hitter",
    positions: ["OF"],
    battingOrder: 1,
    salary: 4000,
    projection: 8,
    ceiling: 15,
    value: 2,
    ownership: 20,
    leverage: 5,
    risk: 30,
    confidence: 90,
    lineupStatus: "active",
    eligibilityStatus: "STARTING_HITTER",
    optimizerEligible: true,
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
    fantasyProsProjection: null,
    fantasyProsMatchStatus: null,
    blueCollarProjection: null,
    blueCollarRawProjection: null,
    blueCollarMatchStatus: null,
    mlProjection: null,
    mlDataQualityScore: null,
    mlProjectionStatus: null,
    mlFeatureTimestamp: null,
    ...overrides,
  };
}

function pool(players: PoolPlayerRow[]): OptimizerPoolResult {
  return {
    date: "2026-08-12",
    slateId: "mock-main",
    slateName: "Mock Main (Dev)",
    providerName: "mock_dev_provider",
    isMock: true,
    providerSource: "mock_explicit",
    generatedAt: "2026-08-12T18:00:00Z",
    players,
    activePlayers: players.length,
    pitcherCount: 0,
    hitterCount: players.length,
    hasExternalProjections: false,
    externalProviderName: null,
    hasAiProjections: false,
    hasNativeProjections: false,
    hasFantasyProsProjections: false,
    hasMlProjections: false,
    hasBlueCollarProjections: false,
    blueCollarSlateName: null,
    blueCollarSlateMatchStatus: null,
    blueCollarUpdated: null,
    blueCollarCoverage: { returned: 0, usable: 0, identityResolved: 0, eligible: 0, optimizerReady: 0 },
    confirmedLineupGames: 1,
    unconfirmedLineupGames: 0,
    unmatchedCount: 0,
    slateGames: 1,
    rosterFeasibilityPass: true,
    salaryCap: 50000,
    hasOwnership: true,
    vegasCoverage: { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0, games: [] },
    dataStatus: "fresh",
    artifactAgeSeconds: 0,
    lastUpdatedAt: "2026-01-01T00:00:00.000Z",
    eligibilityComputedAt: null,
  };
}

function defaultProps(overrides: Partial<Parameters<typeof ConstraintsPanel>[0]> = {}) {
  return {
    pool: pool([player({ dkPlayerId: "d1", name: "Locked Guy", team: "PHI" }), player({ dkPlayerId: "d2", name: "Excluded Guy", team: "NYY" })]),
    locks: ["d1"],
    exclusions: ["d2"],
    maxExposure: { d1: 0.5 },
    onUnlock: vi.fn(),
    onUnexclude: vi.fn(),
    onClearExclusions: vi.fn(),
    stackSize: null,
    stackTeam: null,
    onStackSizeChange: vi.fn(),
    onStackTeamChange: vi.fn(),
    allowPitcherVsHitter: false,
    onAllowPitcherVsHitterChange: vi.fn(),
    useProbableStarters: true,
    onUseProbableStartersChange: vi.fn(),
    minSalary: null,
    onMinSalaryChange: vi.fn(),
    minUnique: 2,
    onMinUniqueChange: vi.fn(),
    ...overrides,
  };
}

describe("ConstraintsPanel", () => {
  it("lists locked players with their exposure and a Remove control", () => {
    render(<ConstraintsPanel {...defaultProps()} />);
    expect(screen.getByText(/Locked Guy/)).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("calls onUnlock when Remove is clicked on a locked player", () => {
    const onUnlock = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onUnlock })} />);
    fireEvent.click(screen.getByText("Remove"));
    expect(onUnlock).toHaveBeenCalledWith("d1");
  });

  it("lists excluded players with a Restore control", () => {
    render(<ConstraintsPanel {...defaultProps()} />);
    expect(screen.getByText("Excluded Guy")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Restore"));
  });

  it("calls onClearExclusions when Clear All is clicked", () => {
    const onClearExclusions = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onClearExclusions })} />);
    fireEvent.click(screen.getByText("Clear All"));
    expect(onClearExclusions).toHaveBeenCalled();
  });

  it("shows friendly empty states when nothing is locked/excluded", () => {
    render(<ConstraintsPanel {...defaultProps({ locks: [], exclusions: [] })} />);
    expect(screen.getByText("No players locked.")).toBeInTheDocument();
    expect(screen.getByText("No players excluded.")).toBeInTheDocument();
  });

  it("calls onStackSizeChange when a primary stack preset is clicked", () => {
    const onStackSizeChange = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onStackSizeChange })} />);
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect(onStackSizeChange).toHaveBeenCalledWith(5);
  });

  it("disables the Stack Team selector until a stack size is chosen", () => {
    render(<ConstraintsPanel {...defaultProps({ stackSize: null })} />);
    expect(screen.getByText("Stack Team").closest("label")!.querySelector("select")).toBeDisabled();
  });

  it("enables the Stack Team selector once a stack size is chosen", () => {
    render(<ConstraintsPanel {...defaultProps({ stackSize: 5 })} />);
    expect(screen.getByText("Stack Team").closest("label")!.querySelector("select")).not.toBeDisabled();
  });

  it("secondary stack presets are shown but disabled, never faking support", () => {
    render(<ConstraintsPanel {...defaultProps()} />);
    const preset = screen.getByText("5 / 2");
    expect(preset.tagName).toBe("SPAN"); // not a clickable button
    expect(preset).toHaveAttribute("title", "Not yet supported by the optimizer");
    expect(screen.getByText(/multi-stack presets are disabled, not faked/i)).toBeInTheDocument();
  });

  it("toggles allowPitcherVsHitter", () => {
    const onAllowPitcherVsHitterChange = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onAllowPitcherVsHitterChange })} />);
    fireEvent.click(screen.getByLabelText("Allow hitters vs opposing pitcher"));
    expect(onAllowPitcherVsHitterChange).toHaveBeenCalledWith(true);
  });

  it("Use Probable Starters is ON by default and can be toggled off", () => {
    const onUseProbableStartersChange = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ useProbableStarters: true, onUseProbableStartersChange })} />);
    const checkbox = screen.getByLabelText("Use Probable Starters") as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);
    expect(onUseProbableStartersChange).toHaveBeenCalledWith(false);
  });

  it("shows the salary cap read-only and reports minSalary changes", () => {
    const onMinSalaryChange = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onMinSalaryChange })} />);
    expect(screen.getByText("$50,000")).toBeInTheDocument();
    const input = screen.getByText("Minimum Spend").closest("label")!.querySelector("input")!;
    fireEvent.change(input, { target: { value: "45000" } });
    expect(onMinSalaryChange).toHaveBeenCalledWith(45000);
  });

  it("reports minUnique changes", () => {
    const onMinUniqueChange = vi.fn();
    render(<ConstraintsPanel {...defaultProps({ onMinUniqueChange })} />);
    const select = screen.getByText("Minimum Unique Players").closest("label")!.querySelector("select")!;
    fireEvent.change(select, { target: { value: "3" } });
    expect(onMinUniqueChange).toHaveBeenCalledWith(3);
  });
});
