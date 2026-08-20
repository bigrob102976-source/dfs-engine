import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlayerDetailModal } from "../PlayerDetailModal";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

function player(overrides: Partial<PoolPlayerRow> = {}): PoolPlayerRow {
  return {
    dkPlayerId: "d1",
    mlbPlayerId: "h1",
    name: "Test Player",
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
    ...overrides,
  };
}

describe("PlayerDetailModal -- FantasyPros comparison row", () => {
  it("shows NOT AVAILABLE when no FantasyPros projection exists for this player, never a fabricated value", () => {
    render(<PlayerDetailModal player={player()} onClose={vi.fn()} />);
    expect(screen.getByText("FantasyPros")).toBeInTheDocument();
    expect(screen.getByText("NOT AVAILABLE")).toBeInTheDocument();
  });

  it("shows the FantasyPros projection when matched", () => {
    render(<PlayerDetailModal player={player({ fantasyProsProjection: 9.85, fantasyProsMatchStatus: "matched" })} onClose={vi.fn()} />);
    expect(screen.getByText("9.8")).toBeInTheDocument();
  });

  it("never lets a FantasyPros value bleed into the Legacy (independent projection) row", () => {
    render(<PlayerDetailModal player={player({ fantasyProsProjection: 999, fantasyProsMatchStatus: "matched", projection: 8 })} onClose={vi.fn()} />);
    expect(screen.getByText("999.0")).toBeInTheDocument(); // FantasyPros cell itself
    expect(screen.getByText("8.0")).toBeInTheDocument(); // Legacy (independent projection) unaffected, not overwritten with 999
  });

  it("shows an ambiguous/unmatched annotation next to the value when the match wasn't clean, without ever affecting whether a value is shown", () => {
    render(<PlayerDetailModal player={player({ fantasyProsProjection: 5.2, fantasyProsMatchStatus: "ambiguous" })} onClose={vi.fn()} />);
    expect(screen.getByText("5.2")).toBeInTheDocument();
    expect(screen.getByText("(ambiguous)")).toBeInTheDocument();
  });
});
