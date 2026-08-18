import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DkSlateCoverageSummary } from "../DkSlateCoverageSummary";
import type { DkSlateVegasCoverage } from "@/lib/dkVegasCoverage";

describe("DkSlateCoverageSummary", () => {
  it("shows a placeholder when no DK slate is selected", () => {
    const coverage: DkSlateVegasCoverage = { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, games: [] };
    render(<DkSlateCoverageSummary coverage={coverage} />);
    expect(screen.getByText(/No DraftKings slate has been selected/)).toBeInTheDocument();
  });

  it("renders aggregate counts and the per-game coverage table", () => {
    const coverage: DkSlateVegasCoverage = {
      dkGames: 2,
      pregameCovered: 1,
      missing: 0,
      frozen: 1,
      inPlayIgnored: 1,
      invalid: 0,
      notMatched: 0,
      coveragePercent: 50,
      games: [
        {
          gameInfo: "CLE@DET 07:05PM ET", dkAway: "CLE", dkHome: "DET", researchGameId: "g1", matchupLabel: "CLE @ DET",
          gameDatetimeUtc: "2026-08-17T23:05:00Z", mlbStatus: "Final", vegasStatus: "PREGAME_FROZEN", provider: "SportsGameOdds",
          lastPregameUpdate: "2026-08-17T18:00:00Z", booksUsed: ["draftkings", "fanduel"], consensusTotal: 8.5, awayImplied: 4.0, homeImplied: 4.5,
        },
        {
          gameInfo: "BOS@NYY 07:05PM ET", dkAway: "BOS", dkHome: "NYY", researchGameId: "g2", matchupLabel: "BOS @ NYY",
          gameDatetimeUtc: "2026-08-17T23:05:00Z", mlbStatus: "In Progress", vegasStatus: "IN_PLAY_ONLY", provider: "SportsGameOdds",
          lastPregameUpdate: null, booksUsed: [], consensusTotal: null, awayImplied: null, homeImplied: null,
        },
      ],
    };
    render(<DkSlateCoverageSummary coverage={coverage} />);

    expect(screen.getByText("DK Games")).toBeInTheDocument();
    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
    expect(screen.getByText("BOS @ NYY")).toBeInTheDocument();
    expect(screen.getByText("PREGAME FROZEN")).toBeInTheDocument();
    expect(screen.getByText("IN-PLAY ONLY")).toBeInTheDocument();
  });
});
