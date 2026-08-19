import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlateRankingsColumn } from "../SlateRankingsColumn";
import { buildGameRankings, type AiRankedPlayer } from "@/lib/commandCenter";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";
import type { PlayerRow } from "@/lib/types";

const GAME = buildGameEnvironmentReport({ home_team: "DET", away_team: "CLE" });
const RANKINGS = buildGameRankings(
  { slate_date: "2026-08-14", generated_at: "2026-08-14T18:00:00Z", engine_version: "0.1.0", games: [GAME], vegas_slate_analysis: null, warnings: [] },
  null,
);

function renderColumn() {
  return render(<SlateRankingsColumn rankings={RANKINGS} pitcherRecords={[]} hitterRows={[]} pitcherRows={[]} analysis={null} />);
}

function aiRow(overrides: Partial<AiRankedPlayer> = {}): AiRankedPlayer {
  const base: PlayerRow = {
    id: "p1", playerType: "hitter", name: "Test Player", team: "DET", opponent: "CLE", gameId: GAME.game_id,
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 10, ceiling: 18, floor: 4,
    overall: 60, power: 60, matchup: 60, risk: 30, confidence: 80, ownership: 15, ownershipTier: "mid",
    chalkScore: 50, leverage: 5, tags: [], reasons: [], lineupStatus: null, matchStatus: null,
    eligibilityStatus: null, optimizerEligible: false, raw: { snapshot: {}, ownership: null, pool: null },
  };
  return { ...base, aiProjection: null, aiDelta: null, aiConfidence: null, aiRisk: null, aiGrade: null, ...overrides };
}

describe("SlateRankingsColumn", () => {
  it("renders a ranking card for each game", () => {
    renderColumn();
    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
  });

  it("shows the empty state when there are no rankings", () => {
    render(<SlateRankingsColumn rankings={[]} pitcherRecords={[]} hitterRows={[]} pitcherRows={[]} analysis={null} />);
    expect(screen.getByText(/No games ranked yet/)).toBeInTheDocument();
  });

  it("opens the Game Center drawer on click and closes it", () => {
    renderColumn();
    fireEvent.click(screen.getByText("CLE @ DET"));
    expect(screen.getByText("Top Hitters")).toBeInTheDocument();
    expect(screen.getByText("AI Summary")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Close"));
    expect(screen.queryByText("AI Summary")).not.toBeInTheDocument();
  });

  it("Game Center links to the team's hitters/pitchers/stacks pages", () => {
    renderColumn();
    fireEvent.click(screen.getByText("CLE @ DET"));
    expect(screen.getByText("DET Stack →")).toHaveAttribute("href", "/dashboard/hitters?team=DET");
    expect(screen.getByText("CLE Stack →")).toHaveAttribute("href", "/dashboard/hitters?team=CLE");
    expect(screen.getByText("All Stacks →")).toHaveAttribute("href", "/dashboard/stacks");
  });

  // Milestone 20: Game Center's Top AI Players / Top AI Stacks / Top AI Pitchers.
  it("shows Top AI Players/Pitchers/Stacks ranked by AI Projection when AI data is present", () => {
    const hitterRows = [
      aiRow({ id: "h1", name: "Big Bat", team: "DET", aiProjection: 15.4, aiGrade: "A" }),
      aiRow({ id: "h2", name: "Small Bat", team: "CLE", aiProjection: 6.1, aiGrade: "C" }),
    ];
    const pitcherRows = [
      aiRow({ id: "p1", name: "Ace Starter", team: "DET", playerType: "pitcher", aiProjection: 22.7, aiGrade: "A+" }),
    ];
    render(<SlateRankingsColumn rankings={RANKINGS} pitcherRecords={[]} hitterRows={hitterRows} pitcherRows={pitcherRows} analysis={null} />);
    fireEvent.click(screen.getByText("CLE @ DET"));

    const playersHeading = screen.getByText("Top AI Players");
    expect(playersHeading).toBeInTheDocument();
    expect(screen.getByText("Top AI Pitchers")).toBeInTheDocument();
    expect(screen.getByText("Top AI Stacks")).toBeInTheDocument();

    // Ace Starter (22.7) should rank above Big Bat (15.4) above Small Bat
    // (6.1) specifically within the "Top AI Players" list.
    const listContainer = playersHeading.parentElement?.nextElementSibling as HTMLElement;
    const items = Array.from(listContainer.querySelectorAll("li")).map((li) => li.textContent);
    expect(items[0]).toContain("Ace Starter");
    expect(items[1]).toContain("Big Bat");
    expect(items[2]).toContain("Small Bat");
  });

  it("shows a not-generated message for AI sections when no AI data exists", () => {
    renderColumn();
    fireEvent.click(screen.getByText("CLE @ DET"));
    expect(screen.getAllByText("No AI Projections yet.").length).toBeGreaterThan(0);
  });
});
