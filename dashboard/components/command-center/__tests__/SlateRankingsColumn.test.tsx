import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlateRankingsColumn } from "../SlateRankingsColumn";
import { buildGameRankings } from "@/lib/commandCenter";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";

const GAME = buildGameEnvironmentReport({ home_team: "DET", away_team: "CLE" });
const RANKINGS = buildGameRankings(
  { slate_date: "2026-08-14", generated_at: "2026-08-14T18:00:00Z", engine_version: "0.1.0", games: [GAME], vegas_slate_analysis: null, warnings: [] },
  null,
);

function renderColumn() {
  return render(<SlateRankingsColumn rankings={RANKINGS} pitcherRecords={[]} hitterRows={[]} pitcherRows={[]} analysis={null} />);
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
});
