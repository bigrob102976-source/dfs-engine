import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PoolTable } from "../PoolTable";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

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

const players = [
  player({ dkPlayerId: "d1", name: "Bravo Hitter", team: "PHI", playerType: "hitter", positions: ["OF"], projection: 5 }),
  player({ dkPlayerId: "d2", name: "Alpha Hitter", team: "NYY", playerType: "hitter", positions: ["1B", "OF"], projection: 15 }),
  player({ dkPlayerId: "d3", name: "Ace Pitcher", team: "TOR", playerType: "pitcher", positions: ["P"], battingOrder: null, projection: 20 }),
];

function renderTable(overrides: Partial<Parameters<typeof PoolTable>[0]> = {}) {
  const onToggleLock = vi.fn();
  const onToggleExclude = vi.fn();
  const onExposureChange = vi.fn();
  render(
    <PoolTable
      players={players}
      locks={new Set()}
      exclusions={new Set()}
      maxExposure={{}}
      onToggleLock={onToggleLock}
      onToggleExclude={onToggleExclude}
      onExposureChange={onExposureChange}
      {...overrides}
    />,
  );
  return { onToggleLock, onToggleExclude, onExposureChange };
}

describe("PoolTable", () => {
  it("renders every player", () => {
    renderTable();
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    expect(screen.getByText("Ace Pitcher")).toBeInTheDocument();
  });

  it("defaults to sorting by projection descending", () => {
    renderTable();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Ace Pitcher"); // projection 20
  });

  it("the P position tab shows only pitchers", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "P" }));
    expect(screen.getByText("Ace Pitcher")).toBeInTheDocument();
    expect(screen.queryByText("Bravo Hitter")).not.toBeInTheDocument();
  });

  it("a multi-position player appears under every eligible position tab", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "1B" }));
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "OF" }));
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
  });

  it("search matches name, team, and opponent", () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText("Search players..."), { target: { value: "phi" } });
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Hitter")).not.toBeInTheDocument();
  });

  it("clicking a sortable header toggles direction", () => {
    renderTable();
    // Anchored regex: the "Legacy" (independent) projection column
    // defaults to showing a sort-direction arrow, e.g. "Legacy ↓", so an
    // exact string match won't work.
    const header = screen.getByRole("columnheader", { name: /^Legacy/ });
    fireEvent.click(header); // ascending
    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Bravo Hitter"); // lowest projection (5) first
    fireEvent.click(header); // descending again
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Ace Pitcher");
  });

  it("calls onToggleLock when the Lock button is clicked", () => {
    const { onToggleLock } = renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Lock Bravo Hitter" }));
    expect(onToggleLock).toHaveBeenCalledWith("d1");
  });

  it("calls onToggleExclude when the Exclude button is clicked", () => {
    const { onToggleExclude } = renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Exclude Bravo Hitter" }));
    expect(onToggleExclude).toHaveBeenCalledWith("d1");
  });

  it("highlights a locked row and disables its exclude button", () => {
    renderTable({ locks: new Set(["d1"]) });
    expect(screen.getByRole("button", { name: "Unlock Bravo Hitter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exclude Bravo Hitter" })).toBeDisabled();
  });

  it("highlights an excluded row and disables its lock button", () => {
    renderTable({ exclusions: new Set(["d1"]) });
    expect(screen.getByRole("button", { name: "Restore Bravo Hitter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lock Bravo Hitter" })).toBeDisabled();
  });

  it("calls onExposureChange with a fraction when the exposure input changes", () => {
    const { onExposureChange } = renderTable();
    const row = screen.getByText("Bravo Hitter").closest("tr")!;
    const input = row.querySelector("input[type='number']") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "50" } });
    expect(onExposureChange).toHaveBeenCalledWith("d1", 0.5);
  });

  it("shows an empty state when no players match the filters", () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText("Search players..."), { target: { value: "zzz-nobody" } });
    expect(screen.getByText("No players match the current filters.")).toBeInTheDocument();
  });

  it("blanks batting order for pitchers", () => {
    renderTable();
    const row = screen.getByText("Ace Pitcher").closest("tr")!;
    const cells = Array.from(row.querySelectorAll("td")).map((td) => td.textContent);
    // Ord column is the 7th cell (Lock, Exclude, Pos, Name, Team, Opp, Ord, ...)
    expect(cells[6]).toBe("");
  });

  it("does not show projection comparison columns by default", () => {
    renderTable();
    expect(screen.queryByRole("columnheader", { name: "BlueCollar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "BC Δ" })).not.toBeInTheDocument();
  });

  it("shows BlueCollar/BC Adj/BC Δ columns when showProjectionComparison is true", () => {
    const comparisonPlayers = [
      player({ dkPlayerId: "d1", name: "Schwarber", projection: 11.9, externalProjection: 11.2, adjustedProjection: 12.1, adjustmentDelta: 0.9 }),
    ];
    render(
      <PoolTable
        players={comparisonPlayers}
        locks={new Set()}
        exclusions={new Set()}
        maxExposure={{}}
        onToggleLock={vi.fn()}
        onToggleExclude={vi.fn()}
        onExposureChange={vi.fn()}
        showProjectionComparison
      />,
    );
    expect(screen.getByRole("columnheader", { name: "BlueCollar" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "BC Adj" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "BC Δ" })).toBeInTheDocument();
    const row = screen.getByText("Schwarber").closest("tr")!;
    expect(row.textContent).toContain("11.2");
    expect(row.textContent).toContain("12.1");
    expect(row.textContent).toContain("+0.9");
  });

  it("clicking a player name opens the detail modal with the projection comparison", () => {
    const comparisonPlayers = [
      player({
        dkPlayerId: "d1", name: "Schwarber", team: "PHI", projection: 11.9, externalProjection: 11.2,
        adjustedProjection: 12.1, adjustmentDelta: 0.9, adjustmentPercent: 8.0, adjustmentReasons: ["positive recent hard-hit trend"],
      }),
    ];
    render(
      <PoolTable
        players={comparisonPlayers}
        locks={new Set()}
        exclusions={new Set()}
        maxExposure={{}}
        onToggleLock={vi.fn()}
        onToggleExclude={vi.fn()}
        onExposureChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Schwarber" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Projection Comparison")).toBeInTheDocument();
    expect(screen.getByText(/positive recent hard-hit trend/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("the detail modal shows a plain message when a player has no external projection data", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Bravo Hitter" }));
    expect(screen.getByText("BlueCollar: NOT LOADED for this player.")).toBeInTheDocument();
  });

  // Milestone 20: AI Projection Engine columns + Player Detail section.
  it("always shows BM AI/AI Δ/AI Conf/AI Grade columns and renders each player's AI values", () => {
    const aiPlayers = [
      player({
        dkPlayerId: "d1", name: "Judge", projection: 12, aiProjection: 14.02, aiDelta: 2.02, aiConfidence: 81.2, aiGrade: "A+",
      }),
    ];
    render(
      <PoolTable players={aiPlayers} locks={new Set()} exclusions={new Set()} maxExposure={{}} onToggleLock={vi.fn()} onToggleExclude={vi.fn()} onExposureChange={vi.fn()} />,
    );
    expect(screen.getByRole("columnheader", { name: "BM AI" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "AI Δ" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "AI Conf" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "AI Grade" })).toBeInTheDocument();
    const row = screen.getByText("Judge").closest("tr")!;
    expect(row.textContent).toContain("14.0");
    expect(row.textContent).toContain("+2.02");
    expect(row.textContent).toContain("81");
    expect(row.textContent).toContain("A+");
  });

  // Milestone 27: Native Projection columns -- always shown (never
  // gated behind showProjectionComparison, matching AI's own columns),
  // labeled unambiguously "BM Native"/"Native Δ" per lib/projectionLabels.ts.
  it("always shows BM Native/Native Δ columns and renders each player's Native values", () => {
    const nativePlayers = [
      player({ dkPlayerId: "d1", name: "Ohtani", projection: 15, nativeProjection: 16.4, nativeDelta: 1.4 }),
    ];
    render(
      <PoolTable players={nativePlayers} locks={new Set()} exclusions={new Set()} maxExposure={{}} onToggleLock={vi.fn()} onToggleExclude={vi.fn()} onExposureChange={vi.fn()} />,
    );
    expect(screen.getByRole("columnheader", { name: "BM Native" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Native Δ" })).toBeInTheDocument();
    const row = screen.getByText("Ohtani").closest("tr")!;
    expect(row.textContent).toContain("16.4");
    expect(row.textContent).toContain("+1.4");
  });

  it("AI columns render '--' for a player with no AI Projection yet", () => {
    renderTable();
    const row = screen.getByText("Bravo Hitter").closest("tr")!;
    // Salary/Value/Own% etc. also render "--" for missing data, so this
    // just confirms the new columns don't throw or render a stray "null".
    expect(row.textContent).not.toContain("null");
    expect(row.textContent).not.toContain("undefined");
  });

  it("clicking a player with AI data opens the AI Projection Engine section with signal breakdown and reasons", () => {
    const aiPlayers = [
      player({
        dkPlayerId: "d1", name: "Judge", team: "NYY", projection: 12, aiProjection: 14.02, aiCeiling: 23.37, aiFloor: 7.01,
        aiDelta: 2.02, aiConfidence: 81.2, aiRisk: 35, aiGrade: "A+", aiValueScore: 2.42,
        aiSignals: [{ category: "weather", label: "Weather", raw_delta: 0.45, weight: 1, delta: 0.45, reason: "Wind Out 14 MPH" }],
        aiReasons: ["Weather +0.45: Wind Out 14 MPH"],
        aiSummary: "Judge projects to 14.0 AI points (confidence 81, risk 35) with positive Weather signals.",
      }),
    ];
    render(
      <PoolTable players={aiPlayers} locks={new Set()} exclusions={new Set()} maxExposure={{}} onToggleLock={vi.fn()} onToggleExclude={vi.fn()} onExposureChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Judge" }));
    expect(screen.getByText("Big Money AI")).toBeInTheDocument();
    expect(screen.getByText("Signal Breakdown")).toBeInTheDocument();
    expect(screen.getByText(/Wind Out 14 MPH/)).toBeInTheDocument();
    expect(screen.getByText(/projects to 14.0 AI points/)).toBeInTheDocument();
  });

  it("the AI Projection Engine section shows a not-generated message for a player without AI data", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Bravo Hitter" }));
    expect(screen.getByText(/No AI Projection generated yet/)).toBeInTheDocument();
  });
});
