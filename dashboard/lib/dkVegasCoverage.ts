import type { GameEnvironmentReport, SlateEnvironmentReport } from "./gameEnvironment";

// Milestone 25 -- DK Slate Coverage Monitor. Pure, read-only derivation
// layer, same pattern as vegasIntelligence.ts: scopes Vegas pregame
// coverage to the games ACTUALLY on the selected real DraftKings slate
// (dfs/slate_validation.py's dk_game_matches, already computed and saved
// in dk_match_report_<timestamp>.json by the existing DK-pool-build
// pipeline -- never "however many MLB events SportsGameOdds returned").

export type VegasCoverageStatus = "LIVE_PREGAME" | "PREGAME_FROZEN" | "MISSING" | "INVALID" | "IN_PLAY_ONLY" | "NOT_MATCHED";

export interface DkSlateGameCoverage {
  gameInfo: string;
  dkAway: string | null;
  dkHome: string | null;
  researchGameId: string | null;
  matchupLabel: string;
  gameDatetimeUtc: string | null;
  mlbStatus: string | null;
  vegasStatus: VegasCoverageStatus;
  provider: string | null;
  lastPregameUpdate: string | null;
  booksUsed: string[];
  consensusTotal: number | null;
  awayImplied: number | null;
  homeImplied: number | null;
  // Milestone 27: multi-provider provenance, straight from VegasSnapshot.
  selectedProvider: string | null;
  fallbackUsed: boolean;
  primaryProviderStatus: string | null;
  secondaryProviderStatus: string | null;
  missingReason: string | null;
}

export interface DkSlateVegasCoverage {
  dkGames: number;
  pregameCovered: number;
  missing: number;
  frozen: number;
  inPlayIgnored: number;
  invalid: number;
  notMatched: number;
  coveragePercent: number;
  // Milestone 27: split of `pregameCovered` by which provider actually
  // supplied it -- "Primary Covered" (SportsGameOdds, never a fallback)
  // vs "Fallback Covered" (The Odds API stepped in). primaryCovered +
  // fallbackCovered === pregameCovered always.
  primaryCovered: number;
  fallbackCovered: number;
  games: DkSlateGameCoverage[];
}

interface RawDkGameMatch {
  status?: unknown;
  research_game_id?: unknown;
  dk_away?: unknown;
  dk_home?: unknown;
}

function emptyCoverage(): DkSlateVegasCoverage {
  return { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0, games: [] };
}

function findGame(report: SlateEnvironmentReport | null, gameId: string): GameEnvironmentReport | null {
  if (!report) return null;
  return report.games.find((g) => g.game_id === gameId) ?? null;
}

/** Scopes Vegas pregame coverage to exactly the games on the selected DK
 * slate (`matchReport.dk_game_matches`, from
 * dfs/persistence.py::save_match_report() via dfs/player_pool.py::
 * build_match_report()) -- never SportsGameOdds' own raw event count.
 * `environmentReport` supplies each matched game's Vegas/MLB-status data;
 * a null/missing report just means every matched game shows MISSING. */
export function buildDkSlateVegasCoverage(
  matchReport: Record<string, unknown> | null,
  environmentReport: SlateEnvironmentReport | null,
): DkSlateVegasCoverage {
  if (!matchReport) return emptyCoverage();

  const rawMatches = matchReport.dk_game_matches;
  if (!rawMatches || typeof rawMatches !== "object") return emptyCoverage();

  const games: DkSlateGameCoverage[] = Object.entries(rawMatches as Record<string, RawDkGameMatch>).map(([gameInfo, m]) => {
    const dkAway = typeof m.dk_away === "string" ? m.dk_away : null;
    const dkHome = typeof m.dk_home === "string" ? m.dk_home : null;
    const researchGameId = typeof m.research_game_id === "string" ? m.research_game_id : null;
    const matched = m.status === "matched" && researchGameId !== null;

    if (!matched) {
      return {
        gameInfo,
        dkAway,
        dkHome,
        researchGameId: null,
        matchupLabel: dkAway && dkHome ? `${dkAway} @ ${dkHome}` : gameInfo,
        gameDatetimeUtc: null,
        mlbStatus: null,
        vegasStatus: "NOT_MATCHED" as VegasCoverageStatus,
        provider: null,
        lastPregameUpdate: null,
        booksUsed: [],
        consensusTotal: null,
        awayImplied: null,
        homeImplied: null,
        selectedProvider: null,
        fallbackUsed: false,
        primaryProviderStatus: null,
        secondaryProviderStatus: null,
        missingReason: null,
      };
    }

    const game = findGame(environmentReport, researchGameId);
    const vegas = game?.vegas ?? null;
    const vegasStatus: VegasCoverageStatus = vegas ? vegas.vegas_projection_status : "MISSING";

    return {
      gameInfo,
      dkAway,
      dkHome,
      researchGameId,
      matchupLabel: game ? `${game.away_team} @ ${game.home_team}` : (dkAway && dkHome ? `${dkAway} @ ${dkHome}` : gameInfo),
      gameDatetimeUtc: game?.game_datetime_utc ?? null,
      mlbStatus: game?.mlb_game_status ?? null,
      vegasStatus,
      provider: vegas?.provider_name ?? null,
      lastPregameUpdate: vegas && (vegasStatus === "LIVE_PREGAME" || vegasStatus === "PREGAME_FROZEN") ? vegas.retrieved_at : null,
      booksUsed: vegas?.books_used ?? [],
      consensusTotal: vegas?.current_home.total ?? null,
      awayImplied: vegas?.away_implied_runs ?? null,
      homeImplied: vegas?.home_implied_runs ?? null,
      selectedProvider: vegas?.selected_provider ?? null,
      fallbackUsed: vegas?.fallback_used ?? false,
      primaryProviderStatus: vegas?.primary_provider_status ?? null,
      secondaryProviderStatus: vegas?.secondary_provider_status ?? null,
      missingReason: vegas?.missing_reason ?? null,
    };
  });

  games.sort((a, b) => (a.gameDatetimeUtc ?? a.gameInfo).localeCompare(b.gameDatetimeUtc ?? b.gameInfo));

  const dkGames = games.length;
  const frozen = games.filter((g) => g.vegasStatus === "PREGAME_FROZEN").length;
  const livePregame = games.filter((g) => g.vegasStatus === "LIVE_PREGAME").length;
  const inPlayIgnored = games.filter((g) => g.vegasStatus === "IN_PLAY_ONLY").length;
  const invalid = games.filter((g) => g.vegasStatus === "INVALID").length;
  const notMatched = games.filter((g) => g.vegasStatus === "NOT_MATCHED").length;
  const missing = games.filter((g) => g.vegasStatus === "MISSING").length;
  const pregameCovered = livePregame + frozen;
  const coveredGames = games.filter((g) => g.vegasStatus === "LIVE_PREGAME" || g.vegasStatus === "PREGAME_FROZEN");
  const fallbackCovered = coveredGames.filter((g) => g.fallbackUsed).length;
  const primaryCovered = coveredGames.length - fallbackCovered;

  return {
    dkGames,
    pregameCovered,
    missing,
    frozen,
    inPlayIgnored,
    invalid,
    notMatched,
    coveragePercent: dkGames > 0 ? Math.round((pregameCovered / dkGames) * 1000) / 10 : 0,
    primaryCovered,
    fallbackCovered,
    games,
  };
}
