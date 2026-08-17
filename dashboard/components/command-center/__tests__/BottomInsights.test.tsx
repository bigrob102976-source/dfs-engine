import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BottomInsights } from "../BottomInsights";
import type { AiRankedPlayer, AiValuedPlayer, NativeRankedPlayer, NativeValuedPlayer } from "@/lib/commandCenter";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";
import type { PlayerRow } from "@/lib/types";

function playerRow(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "p1", playerType: "hitter", name: "Test Player", team: "DET", opponent: "CLE", gameId: "824238",
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 10, ceiling: 18, floor: 4,
    overall: 60, power: 60, matchup: 60, risk: 30, confidence: 80, ownership: 15, ownershipTier: "mid",
    chalkScore: 50, leverage: 5, tags: [], reasons: [], raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

function aiRow(overrides: Partial<AiRankedPlayer> = {}): AiRankedPlayer {
  return { ...playerRow(overrides), aiProjection: null, aiDelta: null, aiConfidence: null, aiRisk: null, aiGrade: null, ...overrides };
}

function aiValuedRow(overrides: Partial<AiValuedPlayer> = {}): AiValuedPlayer {
  return { ...aiRow(overrides), aiValue: null, ...overrides };
}

function nativeRow(overrides: Partial<NativeRankedPlayer> = {}): NativeRankedPlayer {
  return { ...playerRow(overrides), nativeProjection: null, nativeDelta: null, nativeConfidence: null, ...overrides };
}

function nativeValuedRow(overrides: Partial<NativeValuedPlayer> = {}): NativeValuedPlayer {
  return { ...nativeRow(overrides), nativeValue: null, ...overrides };
}

const GAME = buildGameEnvironmentReport({ home_team: "DET", away_team: "CLE" });

const EMPTY_PROPS = {
  topHitters: [],
  topPitchers: [],
  topStacks: [],
  highestLeverage: [],
  risers: [],
  fallers: [],
  movementFeed: [],
  lockTimes: [],
  topAiValues: [],
  largestAiUpgrades: [],
  largestAiDowngrades: [],
  highestAiConfidence: [],
  lowestAiConfidence: [],
  topNativeProjections: [],
  topNativeValues: [],
  largestNativeVsLegacyDifferences: [],
  highestNativeConfidence: [],
  lowestNativeConfidence: [],
};

describe("BottomInsights", () => {
  it("renders every section header with empty-state messages when nothing is loaded", () => {
    render(<BottomInsights {...EMPTY_PROPS} />);
    expect(screen.getByText("Top 10 Hitters")).toBeInTheDocument();
    expect(screen.getByText("AI Projection Engine")).toBeInTheDocument();
    expect(screen.getByText("Top AI Values")).toBeInTheDocument();
    expect(screen.getByText("Largest AI Upgrades")).toBeInTheDocument();
    expect(screen.getByText("Largest AI Downgrades")).toBeInTheDocument();
    expect(screen.getAllByText("Highest Confidence").length).toBe(2); // AI section + Native section
    expect(screen.getAllByText("Lowest Confidence").length).toBe(2);
    expect(screen.getAllByText("No AI Projections yet.").length).toBe(5);

    expect(screen.getByText("Native Projection Engine")).toBeInTheDocument();
    expect(screen.getByText("Top Native Projections")).toBeInTheDocument();
    expect(screen.getByText("Top Native Values")).toBeInTheDocument();
    expect(screen.getByText("Largest Native vs Legacy Differences")).toBeInTheDocument();
    expect(screen.getAllByText("No Native Projections yet.").length).toBe(5);
  });

  it("renders Top AI Values with the aiValue metric", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        topAiValues={[aiValuedRow({ id: "v1", name: "Value Player", team: "DET", aiValue: 3.14 })]}
      />,
    );
    const row = screen.getByText("Value Player").closest("li")!;
    expect(row.textContent).toContain("3.14");
  });

  it("renders Largest AI Upgrades in green with a + sign, Largest AI Downgrades in red", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        largestAiUpgrades={[aiRow({ id: "u1", name: "Upgraded Player", team: "DET", aiDelta: 1.23 })]}
        largestAiDowngrades={[aiRow({ id: "d1", name: "Downgraded Player", team: "CLE", aiDelta: -0.87 })]}
      />,
    );
    const upRow = screen.getByText("Upgraded Player").closest("li")!;
    expect(upRow.textContent).toContain("+1.23");
    expect(upRow.querySelector(".text-green")).toBeTruthy();

    const downRow = screen.getByText("Downgraded Player").closest("li")!;
    expect(downRow.textContent).toContain("-0.87");
    expect(downRow.querySelector(".text-red")).toBeTruthy();
  });

  it("renders Highest/Lowest Confidence with the aiConfidence metric", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        highestAiConfidence={[aiRow({ id: "h1", name: "Confident Player", team: "DET", aiConfidence: 92 })]}
        lowestAiConfidence={[aiRow({ id: "l1", name: "Uncertain Player", team: "CLE", aiConfidence: 41 })]}
      />,
    );
    expect(screen.getByText("Confident Player").closest("li")!.textContent).toContain("92");
    expect(screen.getByText("Uncertain Player").closest("li")!.textContent).toContain("41");
  });

  it("renders Top Native Projections with the raw projection metric", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        topNativeProjections={[nativeRow({ id: "n1", name: "Projected Player", team: "DET", nativeProjection: 9.6 })]}
      />,
    );
    const row = screen.getByText("Projected Player").closest("li")!;
    expect(row.textContent).toContain("9.6");
  });

  it("renders Top Native Values with the nativeValue metric", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        topNativeValues={[nativeValuedRow({ id: "nv1", name: "Native Value Player", team: "DET", nativeValue: 2.71 })]}
      />,
    );
    const row = screen.getByText("Native Value Player").closest("li")!;
    expect(row.textContent).toContain("2.71");
  });

  it("renders Largest Native vs Legacy Differences with signed deltas", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        largestNativeVsLegacyDifferences={[
          nativeRow({ id: "nd1", name: "Native Up", team: "DET", nativeDelta: 1.5 }),
          nativeRow({ id: "nd2", name: "Native Down", team: "CLE", nativeDelta: -0.9 }),
        ]}
      />,
    );
    const upRow = screen.getByText("Native Up").closest("li")!;
    expect(upRow.textContent).toContain("+1.5");
    expect(upRow.querySelector(".text-green")).toBeTruthy();

    const downRow = screen.getByText("Native Down").closest("li")!;
    expect(downRow.textContent).toContain("-0.9");
    expect(downRow.querySelector(".text-red")).toBeTruthy();
  });

  it("renders Highest/Lowest Native Confidence with the nativeConfidence metric", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        highestNativeConfidence={[nativeRow({ id: "nh1", name: "Confident Native Player", team: "DET", nativeConfidence: 88 })]}
        lowestNativeConfidence={[nativeRow({ id: "nl1", name: "Uncertain Native Player", team: "CLE", nativeConfidence: 22 })]}
      />,
    );
    expect(screen.getByText("Confident Native Player").closest("li")!.textContent).toContain("88");
    expect(screen.getByText("Uncertain Native Player").closest("li")!.textContent).toContain("22");
  });

  it("still renders the pre-existing Top 10 / Leverage / Movement / Lock Times sections unchanged", () => {
    render(
      <BottomInsights
        {...EMPTY_PROPS}
        topHitters={[playerRow({ id: "h1", name: "Top Hitter" })]}
        risers={[{ game: GAME, movement: 0.7 }]}
        lockTimes={[{ game: GAME, gameDatetimeUtc: GAME.game_datetime_utc ?? "2026-08-14T23:10:00Z" }]}
      />,
    );
    expect(screen.getByText("Top Hitter")).toBeInTheDocument();
    expect(screen.getByText("Upcoming Lock Times")).toBeInTheDocument();
  });
});
