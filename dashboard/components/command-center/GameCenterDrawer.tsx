"use client";

import Link from "next/link";

import { VegasExpandedDetail } from "@/components/vegas/VegasExpandedDetail";
import { EnvironmentScoreBadge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Drawer";
import { SectionHeader } from "@/components/ui/Header";
import type { VegasSlateAnalysis } from "@/lib/gameEnvironment";
import { buildAiStackSummaries, type AiRankedPlayer, type GameRanking } from "@/lib/commandCenter";
import type { PitcherRecord } from "@/lib/types";
import { buildVegasGameRows } from "@/lib/vegasIntelligence";

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "--" : v.toFixed(digits);
}

function MiniList({ rows, unit = "" }: { rows: AiRankedPlayer[]; unit?: string }) {
  if (rows.length === 0) return <p className="text-xs text-text-faint">No players yet.</p>;
  return (
    <ul className="flex flex-col gap-1">
      {rows.map((r, i) => (
        <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="w-3 shrink-0 text-text-faint">{i + 1}</span>
            <span className="truncate text-text">{r.name}</span>
          </span>
          <span className="shrink-0 font-semibold text-text">
            {fmt(r.projection)}
            {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Milestone 20's Game Center AI sections: same compact list shape as
 * MiniList, but ranked and displayed by AI Projection (purple, the
 * project's established AI-indicator color) plus AI Grade. */
function AiMiniList({ rows }: { rows: AiRankedPlayer[] }) {
  const withAi = rows.filter((r) => r.aiProjection !== null).sort((a, b) => (b.aiProjection ?? 0) - (a.aiProjection ?? 0));
  if (withAi.length === 0) return <p className="text-xs text-text-faint">No AI Projections yet.</p>;
  return (
    <ul className="flex flex-col gap-1">
      {withAi.map((r, i) => (
        <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="w-3 shrink-0 text-text-faint">{i + 1}</span>
            <span className="truncate text-text">{r.name}</span>
            {r.aiGrade && <span className="shrink-0 text-[10px] font-semibold text-purple">{r.aiGrade}</span>}
          </span>
          <span className="shrink-0 font-semibold text-purple">{fmt(r.aiProjection)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Game Center: the premium slide-over opened by clicking a Slate
 * Rankings card. Reuses components/vegas/VegasExpandedDetail.tsx
 * wholesale for Weather/Bullpen/Park Factor/Pitching Matchup/AI Summary
 * (zero duplicated rendering logic -- exactly the milestone's "No
 * duplicated logic" requirement) and adds compact Top Hitters/Top
 * Pitchers lists for the game's two teams, built from the SAME PlayerRow
 * data already loaded for the rest of the page (no new snapshot reads). */
export function GameCenterDrawer({
  ranking,
  pitcherRecords,
  hitterRows,
  pitcherRows,
  analysis,
  onClose,
}: {
  ranking: GameRanking | null;
  pitcherRecords: PitcherRecord[];
  hitterRows: AiRankedPlayer[];
  pitcherRows: AiRankedPlayer[];
  analysis: VegasSlateAnalysis | null;
  onClose: () => void;
}) {
  if (!ranking) return null;
  const { game } = ranking;

  const vegasRow = buildVegasGameRows([game], pitcherRecords)[0];
  const gameHitters = hitterRows.filter((r) => r.team === game.home_team || r.team === game.away_team);
  const homeHitters = gameHitters.filter((r) => r.team === game.home_team).slice(0, 5);
  const awayHitters = gameHitters.filter((r) => r.team === game.away_team).slice(0, 5);
  const gamePitchers = pitcherRows.filter((r) => r.team === game.home_team || r.team === game.away_team).slice(0, 2);
  const topAiPlayers = [...gameHitters, ...gamePitchers].filter((r) => r.aiProjection !== null).sort((a, b) => (b.aiProjection ?? 0) - (a.aiProjection ?? 0)).slice(0, 5);
  const aiStacks = buildAiStackSummaries(gameHitters, {}).filter((s) => s.team === game.home_team || s.team === game.away_team);

  return (
    <Drawer onClose={onClose} ariaLabel={`${game.away_team} at ${game.home_team} game center`} width="w-[640px]">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-base font-semibold text-text">
            {game.away_team} @ {game.home_team}
          </div>
          <div className="text-xs text-text-faint">{game.venue_name}</div>
        </div>
        <button onClick={onClose} className="text-text-faint hover:text-text" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        <EnvironmentScoreBadge score={ranking.environmentScore} label="ENV" />
        <EnvironmentScoreBadge score={game.environment_score.hitter} label="HIT" />
        <EnvironmentScoreBadge score={game.environment_score.pitcher} label="PIT" orientation="pitching-high" />
        <EnvironmentScoreBadge score={ranking.stackScore} label="STACK" />
        {ranking.vegasScoreValue !== null && <EnvironmentScoreBadge score={ranking.vegasScoreValue} label="VGS" />}
      </div>

      <SectionHeader title="Top Hitters" />
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">{game.away_team}</div>
          <MiniList rows={awayHitters} />
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">{game.home_team}</div>
          <MiniList rows={homeHitters} />
        </div>
      </div>

      <SectionHeader title="Top Pitchers" />
      <div className="mb-4">
        <MiniList rows={gamePitchers} />
      </div>

      {/* Milestone 20: AI Projection Engine sections -- Top AI Players,
          Top AI Stacks, Top AI Pitchers for this game. */}
      <SectionHeader title="Top AI Players" />
      <div className="mb-4">
        <AiMiniList rows={topAiPlayers} />
      </div>

      <SectionHeader title="Top AI Pitchers" />
      <div className="mb-4">
        <AiMiniList rows={gamePitchers} />
      </div>

      <SectionHeader title="Top AI Stacks" />
      <div className="mb-4">
        {aiStacks.length === 0 ? (
          <p className="text-xs text-text-faint">No AI Projections yet.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {aiStacks.map((s, i) => (
              <li key={s.team} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-text">
                  <span className="w-3 shrink-0 text-text-faint">{i + 1}</span>
                  {s.team}
                </span>
                <span className="font-semibold text-purple">{fmt(s.averageProjection)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <SectionHeader title="Stacks" />
      <div className="mb-4 flex gap-2 text-xs">
        <Link href={`/dashboard/hitters?team=${game.away_team}`} className="text-accent hover:text-accent-hover">
          {game.away_team} Stack →
        </Link>
        <Link href={`/dashboard/hitters?team=${game.home_team}`} className="text-accent hover:text-accent-hover">
          {game.home_team} Stack →
        </Link>
        <Link href="/dashboard/stacks" className="text-accent hover:text-accent-hover">
          All Stacks →
        </Link>
      </div>

      <SectionHeader title="Ownership" />
      <div className="mb-4 text-xs text-text-muted">
        {ranking.ownershipScore !== null ? (
          <>
            Combined ownership concentration: <span className="font-semibold text-text">{ranking.ownershipScore.toFixed(0)}</span>
          </>
        ) : (
          <span className="text-text-faint">Ownership has not been projected yet.</span>
        )}
        <Link href="/dashboard/ownership" className="ml-2 text-accent hover:text-accent-hover">
          Full Ownership →
        </Link>
      </div>

      <div className="border-t border-border-subtle pt-3">
        <VegasExpandedDetail row={vegasRow} analysis={analysis} />
      </div>
    </Drawer>
  );
}
