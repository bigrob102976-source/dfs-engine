import Link from "next/link";

import { DataCard } from "@/components/ui/Card";
import { SectionHeader } from "@/components/ui/Header";
import type { GameEnvironmentReport } from "@/lib/gameEnvironment";
import type { AiRankedPlayer, AiValuedPlayer, LineMovementEntry, LockTimeEntry } from "@/lib/commandCenter";
import type { PlayerRow } from "@/lib/types";
import type { StackSummary } from "@/lib/stacks";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}
function matchup(game: GameEnvironmentReport): string {
  return `${game.away_team} @ ${game.home_team}`;
}
function formatLockTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "Time TBD" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function PlayerList({ rows, unit = "" }: { rows: PlayerRow[]; unit?: string }) {
  if (rows.length === 0) return <p className="text-xs text-text-faint">No data yet.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r, i) => (
        <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
          <span className="flex min-w-0 items-center gap-2">
            <span className="w-4 shrink-0 text-text-faint">{i + 1}</span>
            <span className="truncate text-text">{r.name}</span>
            <span className="shrink-0 text-text-faint">{r.team}</span>
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

/** Milestone 20: compact AI-ranked player lists (Top AI Values, Largest
 * AI Upgrades/Downgrades, Highest/Lowest AI Confidence). `metric` picks
 * which AI field is shown on the right -- every value here is joined
 * straight from the AI Projection Engine's snapshot, never recomputed. */
function AiPlayerList({ rows, metric }: { rows: AiRankedPlayer[]; metric: "value" | "delta" | "confidence" }) {
  if (rows.length === 0) return <p className="text-xs text-text-faint">No AI Projections yet.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r, i) => {
        const value =
          metric === "value" ? (r as AiValuedPlayer).aiValue : metric === "delta" ? r.aiDelta : r.aiConfidence;
        const digits = metric === "value" ? 2 : metric === "confidence" ? 0 : 2;
        const signed = metric === "delta" && value !== null && value >= 0;
        return (
          <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
            <span className="flex min-w-0 items-center gap-2">
              <span className="w-4 shrink-0 text-text-faint">{i + 1}</span>
              <span className="truncate text-text">{r.name}</span>
              <span className="shrink-0 text-text-faint">{r.team}</span>
            </span>
            <span className={`shrink-0 font-semibold ${metric === "delta" ? (signed ? "text-green" : "text-red") : "text-purple"}`}>
              {signed ? "+" : ""}
              {fmt(value, digits)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function MovementList({ entries, tone }: { entries: LineMovementEntry[]; tone: "positive" | "negative" }) {
  if (entries.length === 0) return <p className="text-xs text-text-faint">No movement yet.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {entries.slice(0, 5).map(({ game, movement }) => (
        <li key={game.game_id} className="flex items-center justify-between gap-2 text-xs">
          <span className="truncate text-text">{matchup(game)}</span>
          <span className={`shrink-0 font-semibold ${tone === "positive" ? "text-green" : "text-red"}`}>
            {movement > 0 ? "+" : ""}
            {movement.toFixed(1)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** BOTTOM SECTION: Top 10 Hitters/Pitchers/Stacks (the exact
 * `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` shape the existing
 * responsive test already asserts on), Highest Leverage, Biggest
 * Risers/Fallers, Recent Line Movement, Upcoming Lock Times. Every list
 * is a slice/sort of data already loaded for the rest of the page. */
export function BottomInsights({
  topHitters,
  topPitchers,
  topStacks,
  highestLeverage,
  risers,
  fallers,
  movementFeed,
  lockTimes,
  topAiValues,
  largestAiUpgrades,
  largestAiDowngrades,
  highestAiConfidence,
  lowestAiConfidence,
}: {
  topHitters: PlayerRow[];
  topPitchers: PlayerRow[];
  topStacks: StackSummary[];
  highestLeverage: PlayerRow[];
  risers: LineMovementEntry[];
  fallers: LineMovementEntry[];
  movementFeed: LineMovementEntry[];
  lockTimes: LockTimeEntry[];
  topAiValues: AiValuedPlayer[];
  largestAiUpgrades: AiRankedPlayer[];
  largestAiDowngrades: AiRankedPlayer[];
  highestAiConfidence: AiRankedPlayer[];
  lowestAiConfidence: AiRankedPlayer[];
}) {
  return (
    <div>
      <SectionHeader title="Top 10" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <DataCard title="Top 10 Hitters" action={<Link href="/dashboard/hitters" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          <PlayerList rows={topHitters} />
        </DataCard>
        <DataCard title="Top 10 Pitchers" action={<Link href="/dashboard/pitchers" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          <PlayerList rows={topPitchers} />
        </DataCard>
        <DataCard title="Top 10 Stacks" action={<Link href="/dashboard/stacks" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          {topStacks.length === 0 ? (
            <p className="text-xs text-text-faint">No data yet.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {topStacks.map((s, i) => (
                <li key={s.team} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-2 text-text">
                    <span className="w-4 shrink-0 text-text-faint">{i + 1}</span>
                    {s.team}
                  </span>
                  <span className="font-semibold text-text">{fmt(s.averageProjection)}</span>
                </li>
              ))}
            </ul>
          )}
        </DataCard>
      </div>

      <SectionHeader title="Leverage & Movement" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        <DataCard title="Highest Leverage" action={<Link href="/dashboard/ownership" className="text-[11px] text-accent hover:text-accent-hover">Ownership →</Link>}>
          <PlayerList rows={highestLeverage} />
        </DataCard>
        <DataCard title="Biggest Risers">
          <MovementList entries={risers} tone="positive" />
        </DataCard>
        <DataCard title="Biggest Fallers">
          <MovementList entries={fallers} tone="negative" />
        </DataCard>
        <DataCard title="Recent Line Movement" action={<Link href="/dashboard/vegas" className="text-[11px] text-accent hover:text-accent-hover">Vegas →</Link>}>
          {movementFeed.length === 0 ? (
            <p className="text-xs text-text-faint">No line movement yet.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {movementFeed.slice(0, 5).map(({ game, movement }) => (
                <li key={game.game_id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-text">{matchup(game)}</span>
                  <span className={`shrink-0 font-semibold ${movement > 0 ? "text-green" : "text-red"}`}>
                    {movement > 0 ? "+" : ""}
                    {movement.toFixed(1)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DataCard>
      </div>

      <SectionHeader title="AI Projection Engine" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
        <DataCard title="Top AI Values">
          <AiPlayerList rows={topAiValues} metric="value" />
        </DataCard>
        <DataCard title="Largest AI Upgrades">
          <AiPlayerList rows={largestAiUpgrades} metric="delta" />
        </DataCard>
        <DataCard title="Largest AI Downgrades">
          <AiPlayerList rows={largestAiDowngrades} metric="delta" />
        </DataCard>
        <DataCard title="Highest Confidence">
          <AiPlayerList rows={highestAiConfidence} metric="confidence" />
        </DataCard>
        <DataCard title="Lowest Confidence">
          <AiPlayerList rows={lowestAiConfidence} metric="confidence" />
        </DataCard>
      </div>

      <SectionHeader title="Upcoming Lock Times" />
      <div className="mb-6 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        {lockTimes.length === 0 ? (
          <p className="text-xs text-text-faint">No scheduled game times yet.</p>
        ) : (
          <ul className="flex flex-wrap gap-x-6 gap-y-1.5 text-xs">
            {lockTimes.map(({ game, gameDatetimeUtc }) => (
              <li key={game.game_id} className="flex items-center gap-2">
                <span className="font-semibold text-text">{formatLockTime(gameDatetimeUtc)}</span>
                <span className="text-text-faint">{matchup(game)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
