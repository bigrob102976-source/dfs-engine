import Link from "next/link";

import { DataCard } from "@/components/ui/Card";
import { SectionHeader } from "@/components/ui/Header";
import type { GameEnvironmentReport } from "@/lib/gameEnvironment";
import type { AiRankedPlayer, AiValuedPlayer, LineMovementEntry, LockTimeEntry, MlCoverageSummary, NativeRankedPlayer, NativeValuedPlayer } from "@/lib/commandCenter";
import type { PlayerRow } from "@/lib/types";
import type { ScoredStackCandidate, StackCandidate, StackSummary } from "@/lib/stacks";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}
function fmtMoney(v: number | null): string {
  return v === null ? "--" : `$${v.toLocaleString()}`;
}
function fmtPct(v: number | null): string {
  return v === null ? "--" : `${v.toFixed(1)}%`;
}
/** MLB DASHBOARD INTELLIGENCE: probable-vs-confirmed label shown next to
 * a pitcher/hitter name -- reads the SAME eligibilityStatus every other
 * eligibility-aware section of this dashboard already reads (Milestone
 * 30.1/PROBABLE FIX), never a new status classification. */
function starterStatusLabel(eligibilityStatus: string | null): string | null {
  if (eligibilityStatus === "STARTING_PITCHER" || eligibilityStatus === "STARTING_HITTER") return "Confirmed";
  if (eligibilityStatus === "PROBABLE_HITTER") return "Probable";
  return null;
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

/** Milestone 23: compact Native-ranked player lists (Top Native
 * Projections, Top Native Values, Largest Native vs Legacy Differences,
 * Highest/Lowest Native Confidence) -- mirrors AiPlayerList exactly,
 * plus a "projection" metric for the raw-projection ranking AI's
 * section doesn't have. Every value here is joined straight from the
 * Native Projection Model's snapshot, never recomputed. */
function NativePlayerList({ rows, metric }: { rows: NativeRankedPlayer[]; metric: "projection" | "value" | "delta" | "confidence" }) {
  if (rows.length === 0) return <p className="text-xs text-text-faint">No Native Projections yet.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r, i) => {
        const value =
          metric === "projection" ? r.nativeProjection
          : metric === "value" ? (r as NativeValuedPlayer).nativeValue
          : metric === "delta" ? r.nativeDelta
          : r.nativeConfidence;
        const digits = metric === "value" ? 2 : metric === "confidence" ? 0 : metric === "delta" ? 2 : 1;
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

/** MLB DASHBOARD INTELLIGENCE: "Top Stacks" -- ranked by the Big Money
 * Stack Score (lib/stacks.ts::rankStackCandidatesByScore), never
 * fabricated when there aren't enough real eligible hitters to rank
 * (Phase 13). */
function TopStacksList({ candidates }: { candidates: ScoredStackCandidate[] }) {
  if (candidates.length === 0) return <p className="text-xs text-text-faint">Not enough eligible hitters to rank stacks yet.</p>;
  return (
    <ol className="flex flex-col gap-3">
      {candidates.map((c, i) => (
        <li key={c.team} className="border-b border-border pb-2.5 last:border-b-0 last:pb-0">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="flex items-center gap-2 font-semibold text-text">
              <span className="w-4 shrink-0 text-text-faint">{i + 1}</span>
              {c.team}
              {c.status === "WAITING_FOR_LINEUP" && <span className="text-[10px] font-normal text-yellow">Probable</span>}
            </span>
            <span className="shrink-0 font-semibold text-purple">{fmt(c.score, 1)}</span>
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-text-faint sm:grid-cols-4">
            <span>Proj: <span className="text-text">{fmt(c.totalProjection)}</span></span>
            <span>Ceil: <span className="text-text">{fmt(c.totalCeiling)}</span></span>
            <span>Own: <span className="text-text">{fmtPct(c.averageOwnership)}</span></span>
            <span>Value: <span className="text-text">{fmt(c.value, 2)}</span></span>
          </div>
          <p className="mt-1 truncate text-[11px] text-text-faint">
            {c.eligibleHitterCount} eligible · {c.hitters.map((h) => h.name).join(", ")}
          </p>
        </li>
      ))}
    </ol>
  );
}

/** MLB DASHBOARD INTELLIGENCE: "Best Value Pitcher" -- one highlighted
 * card, never fabricated when no eligible pitcher has both a real
 * projection and salary yet (Phase 13). */
function BestValuePitcherCard({ pitcher }: { pitcher: (PlayerRow & { value: number }) | null }) {
  if (!pitcher) return <p className="text-xs text-text-faint">No projected starting pitchers available yet.</p>;
  const status = starterStatusLabel(pitcher.eligibilityStatus);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold text-text">{pitcher.name}</span>
        <span className="shrink-0 text-lg font-semibold text-purple">{pitcher.value.toFixed(2)}</span>
      </div>
      <p className="text-[11px] text-text-faint">
        {pitcher.team}
        {pitcher.opponent ? ` vs ${pitcher.opponent}` : ""}
        {status ? ` · ${status}` : ""}
      </p>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-4">
        <span className="text-text-faint">Salary <span className="block text-text">{fmtMoney(pitcher.salary)}</span></span>
        <span className="text-text-faint">Projection <span className="block text-text">{fmt(pitcher.projection)}</span></span>
        <span className="text-text-faint">Ceiling <span className="block text-text">{fmt(pitcher.ceiling)}</span></span>
        <span className="text-text-faint">Ownership <span className="block text-text">{fmtPct(pitcher.ownership)}</span></span>
      </div>
    </div>
  );
}

/** MLB DASHBOARD INTELLIGENCE: "Best Value Stack" -- one highlighted
 * card with its real hitters listed, never fabricated when there aren't
 * enough real eligible hitters to rank (Phase 13). */
function BestValueStackCard({ stack }: { stack: StackCandidate | null }) {
  if (!stack) return <p className="text-xs text-text-faint">Not enough eligible hitters to rank stacks yet.</p>;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-text">{stack.team} -- {stack.stackSize}-man</span>
        <span className="shrink-0 text-lg font-semibold text-purple">{stack.value?.toFixed(2) ?? "--"} pts/$1k</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-4">
        <span className="text-text-faint">Salary <span className="block text-text">{fmtMoney(stack.totalSalary)}</span></span>
        <span className="text-text-faint">Projection <span className="block text-text">{fmt(stack.totalProjection)}</span></span>
        <span className="text-text-faint">Ceiling <span className="block text-text">{fmt(stack.totalCeiling)}</span></span>
        <span className="text-text-faint">Ownership <span className="block text-text">{fmtPct(stack.averageOwnership)}</span></span>
      </div>
      <ul className="mt-2 flex flex-col gap-0.5 text-[11px]">
        {stack.hitters.map((h) => (
          <li key={h.id} className="flex items-center justify-between text-text-faint">
            <span className="truncate text-text">{h.name}</span>
            <span>{fmtMoney(h.salary)}</span>
          </li>
        ))}
      </ul>
    </div>
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
  topStackCandidates,
  bestValueStack,
  bestValuePitcher,
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
  topNativeProjections,
  topNativeValues,
  largestNativeVsLegacyDifferences,
  highestNativeConfidence,
  lowestNativeConfidence,
  mlCoverage,
}: {
  topHitters: PlayerRow[];
  topPitchers: PlayerRow[];
  topStacks: StackSummary[];
  topStackCandidates: ScoredStackCandidate[];
  bestValueStack: StackCandidate | null;
  bestValuePitcher: (PlayerRow & { value: number }) | null;
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
  topNativeProjections: NativeRankedPlayer[];
  topNativeValues: NativeValuedPlayer[];
  largestNativeVsLegacyDifferences: NativeRankedPlayer[];
  highestNativeConfidence: NativeRankedPlayer[];
  lowestNativeConfidence: NativeRankedPlayer[];
  mlCoverage: MlCoverageSummary;
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

      <SectionHeader title="Stack & Value Intelligence" />
      <div className="mb-6 grid grid-cols-1 gap-3 lg:grid-cols-3">
        <DataCard title="Top Stacks">
          <TopStacksList candidates={topStackCandidates} />
        </DataCard>
        <DataCard title="Best Value Pitcher">
          <BestValuePitcherCard pitcher={bestValuePitcher} />
        </DataCard>
        <DataCard title="Best Value Stack">
          <BestValueStackCard stack={bestValueStack} />
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

      <SectionHeader title="Native Projection Engine" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
        <DataCard title="Top Native Projections">
          <NativePlayerList rows={topNativeProjections} metric="projection" />
        </DataCard>
        <DataCard title="Top Native Values">
          <NativePlayerList rows={topNativeValues} metric="value" />
        </DataCard>
        <DataCard title="Largest Native vs Legacy Differences">
          <NativePlayerList rows={largestNativeVsLegacyDifferences} metric="delta" />
        </DataCard>
        <DataCard title="Highest Confidence">
          <NativePlayerList rows={highestNativeConfidence} metric="confidence" />
        </DataCard>
        <DataCard title="Lowest Confidence">
          <NativePlayerList rows={lowestNativeConfidence} metric="confidence" />
        </DataCard>
      </div>

      {/* Milestone 32.2B: Big Money ML -- SHADOW MODE, informational
          coverage only. Never affects Top Pitchers or any recommendation
          above; comparison lives in the Projection Lab / Pitcher Board. */}
      <SectionHeader title="Big Money ML (Shadow)" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3">
        <DataCard title="Big Money ML Pitchers" action={<Link href="/dashboard/projections" className="text-[11px] text-accent hover:text-accent-hover">Projection Lab →</Link>}>
          <div className="text-xl font-semibold text-text">
            {mlCoverage.projectedPitchers} / {mlCoverage.eligiblePitchers}
            <span className="ml-1 text-xs font-normal text-text-faint">projected</span>
          </div>
          <p className="mt-1 text-[11px] text-text-faint">Shadow evaluation only -- does not affect Top Pitchers or lineup construction.</p>
        </DataCard>
        <DataCard title="Big Money ML Hitters" action={<Link href="/dashboard/projections" className="text-[11px] text-accent hover:text-accent-hover">Projection Lab →</Link>}>
          <div className="text-xl font-semibold text-text">
            {mlCoverage.projectedHitters} / {mlCoverage.eligibleHitters}
            <span className="ml-1 text-xs font-normal text-text-faint">projected</span>
          </div>
          <p className="mt-1 text-[11px] text-text-faint">Shadow evaluation only -- does not affect Top Hitters or lineup construction.</p>
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
