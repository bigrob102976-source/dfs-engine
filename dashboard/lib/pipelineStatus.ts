import { pipelineStageStatus } from "./health";
import {
  loadLatestBatterSnapshot,
  loadLatestDKPlayerPool,
  loadLatestDkMatchReport,
  loadLatestLineupSet,
  loadLatestOwnershipEvaluation,
  loadLatestOwnershipSnapshot,
  loadLatestPitcherSnapshot,
  loadResearchSlate,
} from "./loaders";
import type { ArtifactStatus } from "./types";

function ts(generatedAtUtc?: string | null, generatedAtLocal?: string | null, fallback?: string | null) {
  return { generatedAtUtc: generatedAtUtc ?? fallback ?? null, generatedAtLocal: generatedAtLocal ?? null };
}

/** Builds the Page 1 "Today's Slate" status cards, in pipeline order.
 * Each stage's "outdated" check compares it against the PREVIOUS stage's
 * timestamp -- a real staleness signal (e.g. ownership computed before
 * the DK pool it should have used was last rebuilt). */
export function buildPipelineStatuses(date: string | null): ArtifactStatus[] {
  if (!date) {
    return [];
  }

  const research = loadResearchSlate(date);
  const pitcher = loadLatestPitcherSnapshot(date);
  const batter = loadLatestBatterSnapshot(date);
  const ownership = loadLatestOwnershipSnapshot(date);
  const pool = loadLatestDKPlayerPool(date);
  const lineups = loadLatestLineupSet(date);
  const evaluation = loadLatestOwnershipEvaluation(date);

  const researchTs = ts(null, null, null);
  const pitcherTs = ts(pitcher.data?.generated_at_utc, pitcher.data?.generated_at_local, pitcher.data?.generated_at);
  const batterTs = ts(batter.data?.generated_at_utc, batter.data?.generated_at_local, batter.data?.generated_at);
  const ownershipTs = ts(ownership.data?.generated_at_utc, ownership.data?.generated_at_local, ownership.data?.generated_at);
  const poolTs = ts(pool.data?.generated_at_utc, null, pool.data?.generated_at_utc);
  const lineupsTs = ts(lineups.data?.generated_at_utc, lineups.data?.generated_at_local, lineups.data?.generated_at);
  const evalTs = ts(evaluation.data?.generated_at_utc, evaluation.data?.generated_at_local, evaluation.data?.generated_at);

  return [
    {
      label: "Research Package",
      state: pipelineStageStatus({ exists: !!research.data }),
      path: research.path,
      ...researchTs,
      detail: "Run scripts/build_research_package.py",
      helpCommand: `python scripts/build_research_package.py --date ${date}`,
    },
    {
      label: "Pitcher Snapshot",
      state: pipelineStageStatus({ exists: !!pitcher.data, generatedAtUtc: pitcherTs.generatedAtUtc }),
      path: pitcher.path,
      ...pitcherTs,
      detail: "Not generated yet.",
      helpCommand: `python scripts/run_real_pitcher_agent.py --date ${date}`,
    },
    {
      label: "Batter Snapshot",
      state: pipelineStageStatus({ exists: !!batter.data, generatedAtUtc: batterTs.generatedAtUtc }),
      path: batter.path,
      ...batterTs,
      detail: "Not generated yet.",
      helpCommand: `python scripts/run_real_batter_agent.py --date ${date}`,
    },
    {
      label: "Ownership",
      state: pipelineStageStatus({
        exists: !!ownership.data,
        generatedAtUtc: ownershipTs.generatedAtUtc,
        upstreamGeneratedAtUtc: poolTs.generatedAtUtc,
      }),
      path: ownership.path,
      ...ownershipTs,
      detail: "Ownership has not been generated yet.",
      helpCommand: `python scripts/project_dk_ownership.py --date ${date} --pool <dk_player_pool_path>`,
    },
    {
      label: "DK Salary Import",
      state: pipelineStageStatus({ exists: !!pool.data, generatedAtUtc: poolTs.generatedAtUtc }),
      path: pool.path,
      ...poolTs,
      detail: "No DraftKings salary file imported yet.",
      helpCommand: `python scripts/build_dk_player_pool.py --date ${date} --csv <DKSalaries.csv>`,
    },
    {
      label: "Optimizer",
      state: pipelineStageStatus({
        exists: !!lineups.data,
        generatedAtUtc: lineupsTs.generatedAtUtc,
        upstreamGeneratedAtUtc: poolTs.generatedAtUtc,
      }),
      path: lineups.path,
      ...lineupsTs,
      detail: "No lineups generated yet.",
      helpCommand: `python scripts/optimize_dk_lineups.py --date ${date} --pool <dk_player_pool_path>`,
    },
    {
      label: "Evaluation",
      state: pipelineStageStatus({ exists: !!evaluation.data, generatedAtUtc: evalTs.generatedAtUtc }),
      path: evaluation.path,
      ...evalTs,
      detail: "No evaluation run yet (requires a contest results export).",
      helpCommand: `python scripts/evaluate_dk_ownership.py --date ${date} --ownership <path> --results <contest.csv>`,
    },
  ];
}

export interface SlateSummary {
  gamesOnResearch: number;
  gamesOnDkSlate: number | null;
  postedLineupGames: number;
  missingLineupGames: number;
}

export function buildSlateSummary(date: string | null): SlateSummary {
  if (!date) return { gamesOnResearch: 0, gamesOnDkSlate: null, postedLineupGames: 0, missingLineupGames: 0 };

  const research = loadResearchSlate(date);
  const batter = loadLatestBatterSnapshot(date);
  const matchReport = loadLatestDkMatchReport(date);

  const gamesOnResearch = research.data?.counts?.games ?? 0;
  const missingLineupGames = batter.data?.missing_lineup_game_ids?.length ?? 0;
  const distinctGamesWithLineups = new Set((batter.data?.hitters ?? []).map((h) => h.game_id)).size;
  const gamesOnDkSlate = typeof matchReport.data?.dk_games_total === "number" ? (matchReport.data.dk_games_total as number) : null;

  return {
    gamesOnResearch,
    gamesOnDkSlate,
    postedLineupGames: distinctGamesWithLineups,
    missingLineupGames,
  };
}
