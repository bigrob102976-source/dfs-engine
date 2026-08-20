import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectionLabTable } from "../ProjectionLabTable";
import type { ProjectionLabRow } from "@/lib/projectionLab";

function row(overrides: Partial<ProjectionLabRow> = {}): ProjectionLabRow {
  return {
    id: "p1",
    name: "Test Player",
    team: "NYY",
    opponent: "BOS",
    gameId: "g1",
    playerType: "hitter",
    position: "OF",
    salary: 5000,
    ownership: 20,
    leverage: 3,
    blueCollarProjection: null,
    nativeProjection: 10,
    nativeConfidence: 80,
    aiProjection: 11,
    aiConfidence: 82,
    fantasyProsProjection: null,
    fantasyProsMatchStatus: null,
    aiVsNativeDelta: 1,
    bigMoneyVsBlueCollarDelta: null,
    fpVsNativeDelta: null,
    fpVsAiDelta: null,
    bigMoneyVsFantasyProsDelta: null,
    actualDkPoints: null,
    eligibilityStatus: "STARTING_HITTER",
    optimizerEligible: true,
    ...overrides,
  };
}

describe("ProjectionLabTable -- FantasyPros column", () => {
  it("renders the FantasyPros column header and FP delta columns", () => {
    render(<ProjectionLabTable rows={[row()]} />);
    expect(screen.getByText("FantasyPros")).toBeInTheDocument();
    expect(screen.getByText("FP vs Native Δ")).toBeInTheDocument();
    expect(screen.getByText("FP vs AI Δ")).toBeInTheDocument();
  });

  it("shows NOT AVAILABLE for a row with no FantasyPros projection, never a fabricated value", () => {
    render(<ProjectionLabTable rows={[row({ fantasyProsProjection: null })]} />);
    expect(screen.getByText("NOT AVAILABLE")).toBeInTheDocument();
  });

  it("shows the real FantasyPros projection and delta values when present", () => {
    render(<ProjectionLabTable rows={[row({ fantasyProsProjection: 9.5, fpVsNativeDelta: -0.5, fpVsAiDelta: -1.5 })]} />);
    expect(screen.getByText("9.5")).toBeInTheDocument();
    expect(screen.getByText("-0.5")).toBeInTheDocument();
    expect(screen.getByText("-1.5")).toBeInTheDocument();
  });
});
