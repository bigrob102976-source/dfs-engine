import Link from "next/link";

import { AiSlateSummaryCard } from "@/components/command-center/AiSlateSummaryCard";
import { BottomInsights } from "@/components/command-center/BottomInsights";
import { CommandCenterHeader } from "@/components/command-center/CommandCenterHeader";
import { QuickActionsPanel } from "@/components/command-center/QuickActionsPanel";
import { SlateKpiGrid } from "@/components/command-center/SlateKpiGrid";
import { SlateRankingsColumn } from "@/components/command-center/SlateRankingsColumn";
import { SlateReadinessCard } from "@/components/command-center/SlateReadinessCard";
import { TeamReadinessTable } from "@/components/command-center/TeamReadinessTable";
import { VegasCoverageCard } from "@/components/command-center/VegasCoverageCard";
import { AiProjectionPerformanceCard } from "@/components/AiProjectionPerformanceCard";
import { StatusCard } from "@/components/StatusCard";
import { DataCard } from "@/components/ui/Card";
import { SectionHeader } from "@/components/ui/Header";
import { loadLatestBlueCollarSnapshot } from "@/lib/blueCollarProjections";
import { buildDkSlateVegasCoverage } from "@/lib/dkVegasCoverage";
import {
  buildGameRankings,
  buildLineMovementFeed,
  buildMlCoverageSummary,
  buildSlateAiSummary,
  buildSlateKpis,
  buildUpcomingLockTimes,
  highestAiConfidence,
  highestNativeConfidence,
  joinAiProjections,
  joinNativeProjections,
  largestAiDowngrades,
  largestAiUpgrades,
  largestNativeVsLegacyDifferences,
  lowestAiConfidence,
  lowestNativeConfidence,
  topAiValues,
  topNativeProjections,
  topNativeValues,
} from "@/lib/commandCenter";
import { getAiProjectionByPlayerId } from "@/lib/aiProjections";
import { getMlProjectionByPlayerId } from "@/lib/mlProjections";
import { getNativeProjectionByPlayerId } from "@/lib/nativeProjections";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getPublishedVersion } from "@/lib/db/slateStatus";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import {
  loadLatestBatterSnapshot,
  loadLatestDKPlayerPool,
  loadLatestDkMatchReport,
  loadLatestOwnershipSnapshot,
  loadLatestPitcherSnapshot,
  loadLatestProviderSlate,
  loadResearchGames,
} from "@/lib/loaders";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";
import { loadLatestProjectionSourceComparison } from "@/lib/projectionSourceComparison";
import { buildSlateReadinessSummary, buildTeamReadinessRows, computeSlateCompletionStage } from "@/lib/slateReadiness";
import { effectiveGameIds, filterByGameIdField, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";
import { buildStackSummaries } from "@/lib/stacks";
import { recomputeVegasSlateAnalysis } from "@/lib/vegasIntelligence";
import { buildYesterdaySummary, findLatestEvaluatedDate } from "@/lib/yesterday";

export const dynamic = "force-dynamic";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

/** AI Slate Command Center (redesign of /dashboard). Combines existing
 * pages/data -- Game Environment (Vegas/Weather/Bullpen/Park), Pitcher
 * /Batter Agent, Ownership, Stacks -- into one flagship view. Every
 * number traces to an already-built snapshot (see lib/commandCenter.ts);
 * nothing here recomputes a projection, score, or ownership value.
 *
 * Milestone 29: this is now a pure MEMBER consumption view -- no upload,
 * no refresh trigger, no operational controls. RefreshPanel/
 * SlateReadiness/ExternalProjectionsStatusCard (all of which called
 * routes that are admin-only now) were removed; the read-only Artifact
 * Detail status grid stays (it's informational, never actionable). Every
 * admin action that used to live here (Refresh Today's Slate, Refresh
 * Research, Refresh Missing Data) now lives exclusively on
 * /admin/slates. */
export default async function TodaysSlatePage(props: PageProps<"/dashboard">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  // Milestone 29: auto-select the sole published slate when the member
  // hasn't explicitly chosen one -- never silently default to the
  // unfiltered Full Day view when exactly one real published slate exists.
  const slateCtx = await resolveSlateContext(date, slateId, { autoSelectSoleSlate: true });
  const gameIds = effectiveGameIds(slateCtx);
  const selectedSlateId = slateCtx.selected?.slateId ?? null;

  const [
    summary,
    statuses,
    pitcherSnapshotLoaded,
    batterSnapshotLoaded,
    ownershipLoaded,
    fullDayEnvironmentReport,
    matchReportLoaded,
    providerSlateLoaded,
    // Milestone 27.2: without the real DK pool here, a whole real MLB team
    // whose lineup hasn't posted yet (confirmed live: LAD @ COL) never got
    // a row anywhere on Command Center -- see lib/normalize.ts's own
    // Milestone 27.2 docstring for the full root cause.
    dkPoolLoaded,
  ] = await Promise.all([
    buildSlateSummary(date),
    buildPipelineStatuses(date),
    loadLatestPitcherSnapshot(date),
    loadLatestBatterSnapshot(date),
    loadLatestOwnershipSnapshot(date, selectedSlateId),
    loadLatestEnvironmentReport(date),
    loadLatestDkMatchReport(date, selectedSlateId),
    loadLatestProviderSlate(date),
    loadLatestDKPlayerPool(date, selectedSlateId),
  ]);
  const pitcherSnapshot = pitcherSnapshotLoaded.data;
  const batterSnapshot = batterSnapshotLoaded.data;
  const ownership = ownershipLoaded.data;
  const environmentReport = fullDayEnvironmentReport
    ? (() => {
        const games = filterByGameIdField(fullDayEnvironmentReport.games, gameIds);
        return { ...fullDayEnvironmentReport, games, vegas_slate_analysis: recomputeVegasSlateAnalysis(games) };
      })()
    : null;
  const matchReport = matchReportLoaded.data;
  const providerSlate = providerSlateLoaded.data;
  const dkPool = dkPoolLoaded.data;

  const pitcherRows = filterByGameIds(buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, dkPool), gameIds);
  const hitterRows = filterByGameIds(buildHitterRows(batterSnapshot?.hitters ?? [], ownership, dkPool), gameIds);
  const stacks = buildStackSummaries(hitterRows, ownership?.team_popularity ?? {});

  // Milestone 20: AI Projection Engine -- joined onto the same rows
  // above, additive only (nothing above this line changes behavior).
  const aiByPlayerId = await getAiProjectionByPlayerId(date);
  const aiHitterRows = joinAiProjections(hitterRows, aiByPlayerId);
  const aiPitcherRows = joinAiProjections(pitcherRows, aiByPlayerId);
  const aiAllRows = [...aiPitcherRows, ...aiHitterRows];
  const topAiValues10 = topAiValues(aiAllRows, 10);
  const largestAiUpgrades10 = largestAiUpgrades(aiAllRows, 10);
  const largestAiDowngrades10 = largestAiDowngrades(aiAllRows, 10);
  const highestAiConfidence10 = highestAiConfidence(aiAllRows, 10);
  const lowestAiConfidence10 = lowestAiConfidence(aiAllRows, 10);

  // Milestone 23: Native Projection Model -- joined onto the same rows
  // above, additive only (nothing above this line changes behavior).
  const nativeByPlayerId = await getNativeProjectionByPlayerId(date);
  const nativeHitterRows = joinNativeProjections(hitterRows, nativeByPlayerId);
  const nativePitcherRows = joinNativeProjections(pitcherRows, nativeByPlayerId);
  const nativeAllRows = [...nativePitcherRows, ...nativeHitterRows];
  const topNativeProjections10 = topNativeProjections(nativeAllRows, 10);
  const topNativeValues10 = topNativeValues(nativeAllRows, 10);
  const largestNativeVsLegacyDifferences10 = largestNativeVsLegacyDifferences(nativeAllRows, 10);
  const highestNativeConfidence10 = highestNativeConfidence(nativeAllRows, 10);
  const lowestNativeConfidence10 = lowestNativeConfidence(nativeAllRows, 10);

  // Milestone 32.2B/32.3B: Big Money ML -- SHADOW MODE, informational
  // coverage only. Never influences Top Pitchers/Top Hitters or any
  // other Command Center recommendation (see buildMlCoverageSummary's
  // own docstring). Passing both rows lets the summary bucket pitchers
  // and hitters independently in one pass.
  const mlByPlayerId = await getMlProjectionByPlayerId(date);
  const mlCoverage = buildMlCoverageSummary([...pitcherRows, ...hitterRows], mlByPlayerId);

  // M32.7: Slate Readiness / Team Readiness -- pure aggregation over
  // data already loaded above (matchReport, joined Native/AI rows, ML
  // coverage, stacks) plus two additive reads (BlueCollar snapshot,
  // real MLB game status) -- see lib/slateReadiness.ts's own docstring.
  const [blueCollarSnapshot, researchGamesLoaded] = await Promise.all([
    loadLatestBlueCollarSnapshot(date, selectedSlateId),
    loadResearchGames(date),
  ]);
  const allTeams = Array.from(new Set([...pitcherRows, ...hitterRows].map((r) => r.team)));
  const readiness = buildSlateReadinessSummary(matchReport, allTeams, pitcherRows, nativeAllRows, aiAllRows, mlCoverage, blueCollarSnapshot);
  const hasOwnership = new Set((ownership?.players ?? []).map((p) => p.mlb_player_id).filter((id): id is string => Boolean(id)));
  const stackStatusByTeam = new Map(stacks.map((s) => [s.team, s.status]));
  const teamReadinessRows = buildTeamReadinessRows(
    allTeams, pitcherRows, hitterRows, nativeAllRows, aiAllRows, blueCollarSnapshot, hasOwnership, stackStatusByTeam,
  );
  const researchGames = filterByGameIdField(researchGamesLoaded.data ?? [], gameIds);
  const earliestLockTimeUtc = researchGames
    .map((g) => g.game_datetime_utc)
    .filter((v): v is string => Boolean(v))
    .sort()[0] ?? null;
  const completionStage = computeSlateCompletionStage(readiness, researchGames, earliestLockTimeUtc);

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
  const vegasCoverage = buildDkSlateVegasCoverage(matchReport, environmentReport);

  const playerCount = (pitcherSnapshot?.pitcher_count ?? 0) + (batterSnapshot?.hitter_count ?? 0);
  const salaryCoverage = typeof matchReport?.salary_coverage_percent === "number" ? (matchReport.salary_coverage_percent as number) : null;

  const alerts: string[] = [];
  if (summary.missingLineupGames > 0) alerts.push(`${summary.missingLineupGames} game(s) still missing a posted starting lineup.`);
  if (batterSnapshot && ownership === null) alerts.push("Ownership has not been projected yet for this slate.");

  const [yesterday, evaluatedDate] = await Promise.all([buildYesterdaySummary(), findLatestEvaluatedDate()]);
  const projectionComparison = evaluatedDate ? await loadLatestProjectionSourceComparison(evaluatedDate) : null;

  // Milestone 29: when a slate is selected, "Last Updated" reflects the
  // PUBLISHED version's own timestamp (never a Refresh currently in
  // progress on disk) -- the same atomic-member-view guarantee every
  // published_* pointer field on slate_status enforces. Full-day
  // (no slate selected) has no publish concept, so it keeps the
  // existing latest-artifact-timestamp behavior unchanged.
  const publishedVersion = slateCtx.selected ? await getPublishedVersion(date, slateCtx.selected.slateId) : null;
  const lastUpdated =
    publishedVersion?.publishedAt ??
    (statuses
      .map((s) => s.generatedAtUtc)
      .filter((v): v is string => Boolean(v))
      .sort()
      .reverse()[0] ?? (typeof providerSlate?.generated_at_utc === "string" ? (providerSlate.generated_at_utc as string) : null));

  return (
    <div>
      <CommandCenterHeader
        date={date}
        gameCount={environmentReport?.games.length ?? 0}
        providerName={typeof providerSlate?.provider_name === "string" ? (providerSlate.provider_name as string) : null}
        isMock={Boolean(providerSlate?.is_mock)}
        selectedSlateId={typeof providerSlate?.selected_slate_id === "string" ? (providerSlate.selected_slate_id as string) : null}
        lastUpdated={lastUpdated}
        viewingSlateLabel={slateCtx.selected ? formatSlateLabel(slateCtx.selected) : null}
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

      {/* VEGAS COVERAGE (Milestone 25) -- scoped to the selected DK slate, not raw SportsGameOdds event count */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <VegasCoverageCard coverage={vegasCoverage} />
      </div>

      {/* SLATE READINESS / TEAM READINESS (M32.7) */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
        <SlateReadinessCard readiness={readiness} stage={completionStage} />
        <TeamReadinessTable rows={teamReadinessRows} />
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
        topNativeProjections={topNativeProjections10}
        topNativeValues={topNativeValues10}
        largestNativeVsLegacyDifferences={largestNativeVsLegacyDifferences10}
        highestNativeConfidence={highestNativeConfidence10}
        lowestNativeConfidence={lowestNativeConfidence10}
        mlCoverage={mlCoverage}
      />

      <SectionHeader title="Model Health & Pipeline" />
      <div className="mb-6 grid grid-cols-1 gap-3 lg:grid-cols-3">
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
        <AiProjectionPerformanceCard doc={projectionComparison} />
      </div>

      <div className="mt-4">
        <SectionHeader title="Artifact Detail" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {statuses.map((status) => (
            <StatusCard key={status.label} status={status} />
          ))}
        </div>
      </div>
    </div>
  );
}
