import Link from "next/link";

import { AiSlateSummaryCard } from "@/components/command-center/AiSlateSummaryCard";
import { BottomInsights } from "@/components/command-center/BottomInsights";
import { CommandCenterHeader } from "@/components/command-center/CommandCenterHeader";
import { QuickActionsPanel } from "@/components/command-center/QuickActionsPanel";
import { SlateKpiGrid } from "@/components/command-center/SlateKpiGrid";
import { SlateRankingsColumn } from "@/components/command-center/SlateRankingsColumn";
import { ExternalProjectionsStatusCard } from "@/components/ExternalProjectionsStatusCard";
import { RefreshPanel } from "@/components/RefreshPanel";
import { SlateReadiness } from "@/components/SlateReadiness";
import { StatusCard } from "@/components/StatusCard";
import { DataCard } from "@/components/ui/Card";
import { SectionHeader } from "@/components/ui/Header";
import {
  buildGameRankings,
  buildLineMovementFeed,
  buildSlateAiSummary,
  buildSlateKpis,
  buildUpcomingLockTimes,
  highestAiConfidence,
  joinAiProjections,
  largestAiDowngrades,
  largestAiUpgrades,
  lowestAiConfidence,
  topAiValues,
} from "@/lib/commandCenter";
import { getAiProjectionByPlayerId } from "@/lib/aiProjections";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import {
  loadLatestBatterSnapshot,
  loadLatestDkMatchReport,
  loadLatestOwnershipSnapshot,
  loadLatestPitcherSnapshot,
  loadLatestProviderSlate,
} from "@/lib/loaders";
import { getArtifactStatus } from "@/lib/orchestrator/artifactStatus";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";
import { buildStackSummaries } from "@/lib/stacks";
import { buildYesterdaySummary } from "@/lib/yesterday";

export const dynamic = "force-dynamic";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

/** AI Slate Command Center (redesign of /dashboard). Combines existing
 * pages/data -- Game Environment (Vegas/Weather/Bullpen/Park), Pitcher
 * /Batter Agent, Ownership, Stacks -- into one flagship view. Every
 * number traces to an already-built snapshot (see
 * lib/commandCenter.ts); nothing here recomputes a projection, score,
 * or ownership value, and the existing operational widgets (RefreshPanel,
 * SlateReadiness, Artifact Detail, External Projections status) remain
 * on this same page, unchanged, further down. */
export default function TodaysSlatePage() {
  const date = getTodayChicagoDate();
  const summary = buildSlateSummary(date);
  const readiness = getArtifactStatus(date);
  const statuses = buildPipelineStatuses(date);

  const pitcherSnapshot = loadLatestPitcherSnapshot(date).data;
  const batterSnapshot = loadLatestBatterSnapshot(date).data;
  const ownership = loadLatestOwnershipSnapshot(date).data;
  const environmentReport = loadLatestEnvironmentReport(date);
  const matchReport = loadLatestDkMatchReport(date).data;
  const providerSlate = loadLatestProviderSlate(date).data;

  const pitcherRows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, null);
  const hitterRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, null);
  const stacks = buildStackSummaries(hitterRows, ownership?.team_popularity ?? {});

  // Milestone 20: AI Projection Engine -- joined onto the same rows
  // above, additive only (nothing above this line changes behavior).
  const aiByPlayerId = getAiProjectionByPlayerId(date);
  const aiHitterRows = joinAiProjections(hitterRows, aiByPlayerId);
  const aiPitcherRows = joinAiProjections(pitcherRows, aiByPlayerId);
  const aiAllRows = [...aiPitcherRows, ...aiHitterRows];
  const topAiValues10 = topAiValues(aiAllRows, 10);
  const largestAiUpgrades10 = largestAiUpgrades(aiAllRows, 10);
  const largestAiDowngrades10 = largestAiDowngrades(aiAllRows, 10);
  const highestAiConfidence10 = highestAiConfidence(aiAllRows, 10);
  const lowestAiConfidence10 = lowestAiConfidence(aiAllRows, 10);

  const topHitters10 = [...hitterRows].sort((a, b) => (b.projection ?? 0) - (a.projection ?? 0)).slice(0, 10);
  const topPitchers10 = [...pitcherRows].sort((a, b) => (b.projection ?? 0) - (a.projection ?? 0)).slice(0, 10);
  const highestLeverage10 = [...pitcherRows, ...hitterRows]
    .filter((r) => r.leverage !== null)
    .sort((a, b) => (b.leverage ?? 0) - (a.leverage ?? 0))
    .slice(0, 10);

  const kpis = buildSlateKpis({ report: environmentReport, ownership, pitcherRows, stacks });
  const rankings = buildGameRankings(environmentReport, ownership);
  const aiSummaryBullets = buildSlateAiSummary({ report: environmentReport, ownership, pitcherRows, hitterRows, stacks });
  const movement = buildLineMovementFeed(environmentReport);
  const lockTimes = buildUpcomingLockTimes(environmentReport);

  const playerCount = (pitcherSnapshot?.pitcher_count ?? 0) + (batterSnapshot?.hitter_count ?? 0);
  const salaryCoverage = typeof matchReport?.salary_coverage_percent === "number" ? (matchReport.salary_coverage_percent as number) : null;

  const alerts: string[] = [];
  if (summary.missingLineupGames > 0) alerts.push(`${summary.missingLineupGames} game(s) still missing a posted starting lineup.`);
  if (batterSnapshot && ownership === null) alerts.push("Ownership has not been projected yet for this slate.");

  const yesterday = buildYesterdaySummary();

  const lastUpdated =
    statuses
      .map((s) => s.generatedAtUtc)
      .filter((v): v is string => Boolean(v))
      .sort()
      .reverse()[0] ?? (typeof providerSlate?.generated_at_utc === "string" ? (providerSlate.generated_at_utc as string) : null);

  return (
    <div>
      <CommandCenterHeader
        date={date}
        gameCount={environmentReport?.games.length ?? 0}
        providerName={typeof providerSlate?.provider_name === "string" ? (providerSlate.provider_name as string) : null}
        isMock={Boolean(providerSlate?.is_mock)}
        selectedSlateId={typeof providerSlate?.selected_slate_id === "string" ? (providerSlate.selected_slate_id as string) : null}
        lastUpdated={lastUpdated}
      />

      {alerts.length > 0 && (
        <div className="mb-5 rounded-[var(--radius-control)] border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">
          {alerts.map((a, i) => (
            <div key={i}>⚠ {a}</div>
          ))}
        </div>
      )}

      {/* TOP KPI CARDS */}
      <div className="mb-6">
        <SlateKpiGrid kpis={kpis} />
      </div>

      {/* CENTER LAYOUT -- AI Slate Summary / Slate Rankings / Quick Actions */}
      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-[320px_1fr_280px]">
        <div className="min-w-0">
          <AiSlateSummaryCard bullets={aiSummaryBullets} />
        </div>
        <div className="min-w-0">
          <SlateRankingsColumn
            rankings={rankings}
            pitcherRecords={pitcherSnapshot?.pitchers ?? []}
            hitterRows={aiHitterRows}
            pitcherRows={aiPitcherRows}
            analysis={environmentReport?.vegas_slate_analysis ?? null}
          />
        </div>
        <div className="min-w-0">
          <QuickActionsPanel />
        </div>
      </div>

      {/* BOTTOM SECTION */}
      <BottomInsights
        topHitters={topHitters10}
        topPitchers={topPitchers10}
        topStacks={stacks.slice(0, 10)}
        highestLeverage={highestLeverage10}
        risers={movement.risers}
        fallers={movement.fallers}
        movementFeed={movement.feed}
        lockTimes={lockTimes}
        topAiValues={topAiValues10}
        largestAiUpgrades={largestAiUpgrades10}
        largestAiDowngrades={largestAiDowngrades10}
        highestAiConfidence={highestAiConfidence10}
        lowestAiConfidence={lowestAiConfidence10}
      />

      {/* Pipeline operations -- unchanged, existing widgets */}
      <SectionHeader title="Pipeline Operations" />
      <div className="mb-6">
        <RefreshPanel />
      </div>

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
