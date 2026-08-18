import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DkSlateCoverageSummary } from "../DkSlateCoverageSummary";
import type { DkSlateVegasCoverage } from "@/lib/dkVegasCoverage";

describe("DkSlateCoverageSummary", () => {
  it("shows a placeholder when no DK slate is selected", () => {
    const coverage: DkSlateVegasCoverage = {
      dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0,
      coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0, games: [],
    };
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
      primaryCovered: 1,
      fallbackCovered: 0,
      games: [
        {
          gameInfo: "CLE@DET 07:05PM ET", dkAway: "CLE", dkHome: "DET", researchGameId: "g1", matchupLabel: "CLE @ DET",
          gameDatetimeUtc: "2026-08-17T23:05:00Z", mlbStatus: "Final", vegasStatus: "PREGAME_FROZEN", provider: "SportsGameOdds",
          lastPregameUpdate: "2026-08-17T18:00:00Z", booksUsed: ["draftkings", "fanduel"], consensusTotal: 8.5, awayImplied: 4.0, homeImplied: 4.5,
          selectedProvider: "SportsGameOdds", fallbackUsed: false, primaryProviderStatus: "VALID", secondaryProviderStatus: "NOT_CONFIGURED", missingReason: null,
        },
        {
          gameInfo: "BOS@NYY 07:05PM ET", dkAway: "BOS", dkHome: "NYY", researchGameId: "g2", matchupLabel: "BOS @ NYY",
          gameDatetimeUtc: "2026-08-17T23:05:00Z", mlbStatus: "In Progress", vegasStatus: "IN_PLAY_ONLY", provider: "SportsGameOdds",
          lastPregameUpdate: null, booksUsed: [], consensusTotal: null, awayImplied: null, homeImplied: null,
          selectedProvider: null, fallbackUsed: false, primaryProviderStatus: "PREGAME_NOT_AVAILABLE", secondaryProviderStatus: "NOT_CONFIGURED", missingReason: null,
        },
      ],
    };
    render(<DkSlateCoverageSummary coverage={coverage} />);

    expect(screen.getByText("DK Games")).toBeInTheDocument();
    expect(screen.getByText("Primary Covered")).toBeInTheDocument();
    expect(screen.getByText("Fallback Covered")).toBeInTheDocument();
    expect(screen.getByText("Total Covered")).toBeInTheDocument();
    expect(screen.getByText("Coverage %")).toBeInTheDocument();
    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
    expect(screen.getByText("BOS @ NYY")).toBeInTheDocument();
    expect(screen.getByText("PREGAME FROZEN")).toBeInTheDocument();
    expect(screen.getByText("IN-PLAY ONLY")).toBeInTheDocument();
  });

  it("Milestone 27: shows a visible FALLBACK badge when The Odds API supplied a game's data", () => {
    const coverage: DkSlateVegasCoverage = {
      dkGames: 1, pregameCovered: 1, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0,
      coveragePercent: 100, primaryCovered: 0, fallbackCovered: 1,
      games: [
        {
          gameInfo: "LAD@COL 08:10PM ET", dkAway: "LAD", dkHome: "COL", researchGameId: "g3", matchupLabel: "LAD @ COL",
          gameDatetimeUtc: "2026-08-18T02:10:00Z", mlbStatus: "Scheduled", vegasStatus: "LIVE_PREGAME", provider: "The Odds API",
          lastPregameUpdate: "2026-08-17T20:00:00Z", booksUsed: ["draftkings"], consensusTotal: 11.5, awayImplied: 6.0, homeImplied: 5.5,
          selectedProvider: "The Odds API", fallbackUsed: true, primaryProviderStatus: "EVENT_MATCHED_NO_TOTAL", secondaryProviderStatus: "VALID", missingReason: null,
        },
      ],
    };
    render(<DkSlateCoverageSummary coverage={coverage} />);
    expect(screen.getByText("The Odds API")).toBeInTheDocument();
    expect(screen.getByText("Fallback")).toBeInTheDocument();
  });

  it("Milestone 27: shows the root-cause reason for a missing game instead of a bare 'MISSING'", () => {
    const coverage: DkSlateVegasCoverage = {
      dkGames: 1, pregameCovered: 0, missing: 1, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0,
      coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0,
      games: [
        {
          gameInfo: "TEX@LAA 09:05PM ET", dkAway: "TEX", dkHome: "LAA", researchGameId: "g4", matchupLabel: "TEX @ LAA",
          gameDatetimeUtc: "2026-08-18T04:05:00Z", mlbStatus: "Scheduled", vegasStatus: "MISSING", provider: null,
          lastPregameUpdate: null, booksUsed: [], consensusTotal: null, awayImplied: null, homeImplied: null,
          selectedProvider: null, fallbackUsed: false, primaryProviderStatus: "EVENT_NOT_MATCHED", secondaryProviderStatus: "EVENT_NOT_MATCHED", missingReason: "EVENT_NOT_MATCHED",
        },
      ],
    };
    render(<DkSlateCoverageSummary coverage={coverage} />);
    expect(screen.getByText("EVENT_NOT_MATCHED")).toBeInTheDocument();
  });
});
