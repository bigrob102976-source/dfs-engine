import { MetricCard } from "@/components/ui/Card";
import type { VegasSummaryStats } from "@/lib/vegasIntelligence";

function fmt(value: number | null, digits = 1): string {
  return value === null ? "--" : value.toFixed(digits);
}

function signed(value: number | null, digits = 1): string {
  if (value === null) return "--";
  const s = value.toFixed(digits);
  return value > 0 ? `+${s}` : s;
}

function matchup(game: { away_team: string; home_team: string } | null): string | undefined {
  return game ? `${game.away_team} @ ${game.home_team}` : undefined;
}

/** The 8 top summary cards -- Games / Average Total / Highest Total /
 * Lowest Total / Biggest Favorite / Largest Line Move / Largest Total
 * Move / Average Implied Runs. Every value is read directly from
 * stats already computed in lib/vegasIntelligence.ts; nothing here
 * recalculates anything. */
export function VegasSummaryCards({ stats }: { stats: VegasSummaryStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
      <MetricCard label="Games" value={stats.gameCount} />
      <MetricCard label="Average Total" value={fmt(stats.averageTotal)} />
      <MetricCard
        label="Highest Total"
        value={fmt(stats.highestTotal.value)}
        tone="negative"
        trend={<span className="text-[11px] text-text-faint">{matchup(stats.highestTotal.game)}</span>}
      />
      <MetricCard
        label="Lowest Total"
        value={fmt(stats.lowestTotal.value)}
        tone="positive"
        trend={<span className="text-[11px] text-text-faint">{matchup(stats.lowestTotal.game)}</span>}
      />
      <MetricCard
        label="Biggest Favorite"
        value={stats.biggestFavorite.moneyline !== null ? stats.biggestFavorite.moneyline : "--"}
        trend={<span className="text-[11px] text-text-faint">{stats.biggestFavorite.team ?? undefined}</span>}
      />
      <MetricCard
        label="Largest Line Move"
        value={signed(stats.largestLineMove.value, 0)}
        tone={stats.largestLineMove.value === null ? "neutral" : stats.largestLineMove.value > 0 ? "positive" : "negative"}
        trend={<span className="text-[11px] text-text-faint">{matchup(stats.largestLineMove.game)}</span>}
      />
      <MetricCard
        label="Largest Total Move"
        value={signed(stats.largestTotalMove.value)}
        tone={stats.largestTotalMove.value === null ? "neutral" : stats.largestTotalMove.value > 0 ? "positive" : "negative"}
        trend={<span className="text-[11px] text-text-faint">{matchup(stats.largestTotalMove.game)}</span>}
      />
      <MetricCard label="Average Implied Runs" value={fmt(stats.averageImpliedRuns)} />
    </div>
  );
}
