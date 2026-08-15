import Link from "next/link";

import { ExternalProjectionsStatusCard } from "@/components/ExternalProjectionsStatusCard";
import { RefreshPanel } from "@/components/RefreshPanel";
import { SlateReadiness } from "@/components/SlateReadiness";
import { StatusCard } from "@/components/StatusCard";
import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader, SectionHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { loadLatestBatterSnapshot, loadLatestDkMatchReport, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { getArtifactStatus } from "@/lib/orchestrator/artifactStatus";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";
import { buildStackSummaries } from "@/lib/stacks";
import { buildVegasSummaryStats } from "@/lib/vegasIntelligence";
import { buildYesterdaySummary } from "@/lib/yesterday";

export const dynamic = "force-dynamic";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

function StatusTile({ label, ready }: { label: string; ready: boolean }) {
  return (
    <MetricCard
      label={label}
      value={ready ? "READY" : "MISSING"}
      tone={ready ? "positive" : "negative"}
    />
  );
}

function RankedList({ rows, unit = "" }: { rows: Array<{ id: string; name: string; team: string; projection: number | null }>; unit?: string }) {
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

/** Today's Slate is always the current America/Chicago date -- never the
 * newest artifact folder found on disk (that's what /dashboard/history
 * and /dashboard/yesterday are for). Three-row layout: top-line
 * status/counts, then research highlights, then health/accuracy/pipeline
 * -- every number here is read directly from already-computed artifacts,
 * nothing is recalculated on this page. */
export default function TodaysSlatePage() {
  const date = getTodayChicagoDate();
  const summary = buildSlateSummary(date);
  const readiness = getArtifactStatus(date);
  const statuses = buildPipelineStatuses(date);

  const pitcherSnapshot = loadLatestPitcherSnapshot(date).data;
  const batterSnapshot = loadLatestBatterSnapshot(date).data;
  const ownership = loadLatestOwnershipSnapshot(date).data;
  const environmentReport = loadLatestEnvironmentReport(date);
  const vegasStats = environmentReport && environmentReport.games.length > 0 ? buildVegasSummaryStats(environmentReport) : null;
  const matchReport = loadLatestDkMatchReport(date).data;

  const pitcherRows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, null);
  const hitterRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, null);
  const topPitchers = [...pitcherRows].sort((a, b) => (b.projection ?? 0) - (a.projection ?? 0)).slice(0, 5);
  const topHitters = [...hitterRows].sort((a, b) => (b.projection ?? 0) - (a.projection ?? 0)).slice(0, 5);
  const topStacks = buildStackSummaries(hitterRows, ownership?.team_popularity ?? {})
    .sort((a, b) => (b.teamPopularityScore ?? b.averageProjection ?? 0) - (a.teamPopularityScore ?? a.averageProjection ?? 0))
    .slice(0, 3);

  const playerCount = (pitcherSnapshot?.pitcher_count ?? 0) + (batterSnapshot?.hitter_count ?? 0);
  const salaryCoverage = typeof matchReport?.salary_coverage_percent === "number" ? (matchReport.salary_coverage_percent as number) : null;

  const alerts: string[] = [];
  if (summary.missingLineupGames > 0) alerts.push(`${summary.missingLineupGames} game(s) still missing a posted starting lineup.`);
  if (batterSnapshot && ownership === null) alerts.push("Ownership has not been projected yet for this slate.");

  const yesterday = buildYesterdaySummary();

  return (
    <div>
      <PageHeader title="Today's Slate" description={`America/Chicago · ${date}`} />

      {/* TOP ROW -- slate, games, players, research/ownership/optimizer status */}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Today's Slate" value={summary.gamesOnDkSlate ?? "--"} trend={<span className="text-[11px] text-text-faint">DK games</span>} />
        <MetricCard label="Games" value={summary.gamesOnResearch} />
        <MetricCard label="Players" value={playerCount} />
        <StatusTile label="Research" ready={readiness.research} />
        <StatusTile label="Ownership" ready={readiness.ownership} />
        <StatusTile label="Optimizer" ready={readiness.optimizer} />
      </div>

      <div className="mb-6">
        <RefreshPanel />
      </div>

      {/* SECOND ROW -- research highlights */}
      <SectionHeader title="Slate Highlights" />
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <DataCard title="Top Pitchers" action={<Link href="/dashboard/pitchers" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          <RankedList rows={topPitchers} />
        </DataCard>
        <DataCard title="Top Hitters" action={<Link href="/dashboard/hitters" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          <RankedList rows={topHitters} />
        </DataCard>
        <DataCard title="Top Stacks" action={<Link href="/dashboard/stacks" className="text-[11px] text-accent hover:text-accent-hover">View all →</Link>}>
          {topStacks.length === 0 ? (
            <p className="text-xs text-text-faint">No data yet.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {topStacks.map((s) => (
                <li key={s.team} className="flex items-center justify-between text-xs">
                  <span className="text-text">{s.team}</span>
                  <span className="font-semibold text-text">{fmt(s.teamPopularityScore)}</span>
                </li>
              ))}
            </ul>
          )}
        </DataCard>
        <DataCard title="Alerts">
          {alerts.length === 0 ? (
            <p className="text-xs text-green">No alerts -- slate looks clean.</p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-xs text-yellow">
              {alerts.map((a, i) => (
                <li key={i}>⚠ {a}</li>
              ))}
            </ul>
          )}
        </DataCard>
        <DataCard title="Weather" action={<Link href="/dashboard/weather" className="text-[11px] text-accent hover:text-accent-hover">View →</Link>}>
          <p className="text-xs text-text-faint">Not yet available as a dedicated view.</p>
        </DataCard>
        <DataCard title="Vegas" action={<Link href="/dashboard/vegas" className="text-[11px] text-accent hover:text-accent-hover">View →</Link>}>
          {vegasStats && vegasStats.highestTotal.value !== null ? (
            <div className="text-xs">
              <div className="text-text-faint">Highest Total</div>
              <div className="text-lg font-semibold text-text">{vegasStats.highestTotal.value.toFixed(1)}</div>
              {vegasStats.highestTotal.game && (
                <div className="text-text-faint">
                  {vegasStats.highestTotal.game.away_team} @ {vegasStats.highestTotal.game.home_team}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-faint">No Vegas data yet -- generate today&apos;s Game Environment report.</p>
          )}
        </DataCard>
      </div>

      {/* BOTTOM ROW -- model health, recent accuracy, pipeline status */}
      <SectionHeader title="Model Health & Pipeline" />
      <div className="mb-6 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <DataCard title="Model Health" action={<Link href="/dashboard/health" className="text-[11px] text-accent hover:text-accent-hover">Full report →</Link>}>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-text-faint">Salary Coverage</div>
              <div className="text-lg font-semibold text-text">{salaryCoverage !== null ? `${Math.round(salaryCoverage)}%` : "--"}</div>
            </div>
            <div>
              <div className="text-text-faint">Ownership Coverage</div>
              <div className="text-lg font-semibold text-text">
                {ownership ? `${ownership.players.length} / ${playerCount || "--"}` : "--"}
              </div>
            </div>
          </div>
        </DataCard>
        <DataCard title="Recent Accuracy" action={<Link href="/dashboard/yesterday" className="text-[11px] text-accent hover:text-accent-hover">Full report →</Link>}>
          {yesterday.date ? (
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <div className="text-text-faint">Pitcher MAE ({yesterday.date})</div>
                <div className="text-lg font-semibold text-text">{fmt(yesterday.pitcherMae, 2)}</div>
              </div>
              <div>
                <div className="text-text-faint">Ownership MAE</div>
                <div className="text-lg font-semibold text-text">{fmt(yesterday.ownershipMae, 2)}</div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-text-faint">No evaluated slate yet.</p>
          )}
        </DataCard>
      </div>

      <SlateReadiness readiness={readiness} />

      <div className="mt-4">
        <SectionHeader title="Artifact Detail" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {statuses.map((status) => (
            <StatusCard key={status.label} status={status} />
          ))}
        </div>
      </div>

      <div className="mt-6">
        <ExternalProjectionsStatusCard />
      </div>
    </div>
  );
}
