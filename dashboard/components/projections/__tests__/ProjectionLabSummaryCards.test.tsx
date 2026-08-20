import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectionLabSummaryCards } from "../ProjectionLabSummaryCards";
import type { ProjectionLabSummary } from "@/lib/projectionLab";

function summary(overrides: Partial<ProjectionLabSummary> = {}): ProjectionLabSummary {
  return {
    players: 10,
    eligiblePlayers: 5,
    blueCollarCoverage: 0,
    nativeCoverage: 5,
    aiCoverage: 5,
    nativeEligibleCoverage: 5,
    aiEligibleCoverage: 5,
    fantasyProsCoverage: 0,
    averageNativeProjection: 10,
    averageAiProjection: 11,
    averageFantasyProsProjection: null,
    averageAiAdjustment: 1,
    largestAiUpgrade: null,
    largestAiDowngrade: null,
    largestBigMoneyVsBlueCollarDifference: null,
    largestBigMoneyOverFantasyPros: null,
    largestBigMoneyUnderFantasyPros: null,
    ...overrides,
  };
}

describe("ProjectionLabSummaryCards -- FantasyPros cards", () => {
  it("shows FantasyPros coverage measured against eligible players, not every preserved DK row", () => {
    render(<ProjectionLabSummaryCards summary={summary({ eligiblePlayers: 8, fantasyProsCoverage: 2 })} />);
    expect(screen.getByText("2/8 (25%)")).toBeInTheDocument();
  });

  it("shows -- for average FantasyPros projection when nothing is loaded, never a fabricated number", () => {
    render(<ProjectionLabSummaryCards summary={summary({ averageFantasyProsProjection: null })} />);
    const card = screen.getByText("Avg FantasyPros Projection").parentElement!;
    expect(card.textContent).toContain("--");
  });

  it("shows a real average FantasyPros projection when available", () => {
    render(<ProjectionLabSummaryCards summary={summary({ averageFantasyProsProjection: 7.25 })} />);
    expect(screen.getByText("7.3")).toBeInTheDocument();
  });

  it("shows the largest Big Money over/under FantasyPros differences, each with the player's name", () => {
    const overRow = { id: "p1", name: "Over Guy", bigMoneyVsFantasyProsDelta: 3.4 } as never;
    const underRow = { id: "p2", name: "Under Guy", bigMoneyVsFantasyProsDelta: -2.1 } as never;
    render(<ProjectionLabSummaryCards summary={summary({ largestBigMoneyOverFantasyPros: overRow, largestBigMoneyUnderFantasyPros: underRow })} />);
    expect(screen.getByText("+3.4")).toBeInTheDocument();
    expect(screen.getByText("Over Guy")).toBeInTheDocument();
    expect(screen.getByText("-2.1")).toBeInTheDocument();
    expect(screen.getByText("Under Guy")).toBeInTheDocument();
  });

  it("shows -- for over/under FantasyPros cards when there is no such delta yet", () => {
    render(<ProjectionLabSummaryCards summary={summary()} />);
    expect(screen.getByText("Largest Big Money Over FantasyPros").parentElement!.textContent).toContain("--");
    expect(screen.getByText("Largest Big Money Under FantasyPros").parentElement!.textContent).toContain("--");
  });
});
