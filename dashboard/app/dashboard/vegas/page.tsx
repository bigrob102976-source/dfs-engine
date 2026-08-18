import { VegasHeaderActions } from "@/components/vegas/VegasHeaderActions";
import { VegasIntelligenceBoard } from "@/components/vegas/VegasIntelligenceBoard";
import { GenerateEnvironmentButton } from "@/components/environment/GenerateEnvironmentButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildDkSlateVegasCoverage } from "@/lib/dkVegasCoverage";
import { loadEnvironmentReportHistory, loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { loadLatestDkMatchReport, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { effectiveGameIds, filterByGameIdField, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";
import { buildVegasGameRows } from "@/lib/vegasIntelligence";

export const dynamic = "force-dynamic";

/** Vegas Intelligence Board (Milestone DS3): line movement, implied
 * totals, betting trends, and deterministic AI market analysis for
 * today's slate. Reads the same immutable Game Environment snapshot the
 * /dashboard/environment terminal reads (Milestone DS2) -- Vegas data
 * has always lived inside that report, this page is just its dedicated,
 * premium home. Never computes odds, never touches Projections,
 * Ownership, or the Optimizer.
 *
 * Milestone 26: when a slate is selected via the global dropdown, every
 * section on this page (coverage table, game rows, line-movement
 * history) is filtered to exactly that slate's game_ids -- Full Day
 * (the default) shows every MLB game, matching pre-Milestone-26
 * behavior unchanged. */
export default async function VegasPage(props: PageProps<"/dashboard/vegas">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const gameIds = effectiveGameIds(slateCtx);
  const fullDayReport = loadLatestEnvironmentReport(date);
  const report = fullDayReport ? { ...fullDayReport, games: filterByGameIdField(fullDayReport.games, gameIds) } : null;
  const status = await getGameEnvironmentStatus(date);

  if ("error" in status) {
    return (
      <div>
        <PageHeader title="Vegas Intelligence" description="Track line movement, implied totals, betting trends, and AI market analysis." />
        <EmptyState icon="🔌" title="Provider Offline" description="The Vegas data provider could not be reached. Try again shortly." />
      </div>
    );
  }

  if (!report || report.games.length === 0) {
    return (
      <div>
        <PageHeader title="Vegas Intelligence" description="Track line movement, implied totals, betting trends, and AI market analysis." />
        <EmptyState
          icon="🏟"
          title="No Games"
          description="Build a research package from the main dashboard first, then generate today's Game Environment report."
          action={<GenerateEnvironmentButton />}
        />
      </div>
    );
  }

  const gamesWithVegas = report.games.filter((g) => g.vegas !== null);
  if (gamesWithVegas.length === 0) {
    return (
      <div>
        <PageHeader title="Vegas Intelligence" description="Track line movement, implied totals, betting trends, and AI market analysis." />
        <EmptyState
          icon="💰"
          title="Vegas Provider / NOT CONNECTED"
          description="No SPORTSGAMEODDS_API_KEY is configured and mock mode was not explicitly requested, so no Vegas data was collected. Native Projection Vegas Adjustment: DISABLED. Set SPORTSGAMEODDS_API_KEY (server-side only) and regenerate the report to connect a real provider."
          action={<GenerateEnvironmentButton />}
        />
      </div>
    );
  }

  const pitcherSnapshot = loadLatestPitcherSnapshot(date).data;
  const rows = buildVegasGameRows(report.games, pitcherSnapshot?.pitchers ?? []);
  const sampleVegas = gamesWithVegas[0]?.vegas ?? null;
  const fullDayHistory = loadEnvironmentReportHistory(date);
  const history = fullDayHistory.map((h) => ({ ...h, games: filterByGameIdField(h.games, gameIds) }));
  const matchReport = loadLatestDkMatchReport(date, slateCtx.selected?.slateId ?? null).data;
  const coverage = buildDkSlateVegasCoverage(matchReport, report);
  const slateDescription = slateCtx.selected ? ` -- ${formatSlateLabel(slateCtx.selected)}` : "";

  return (
    <div>
      <PageHeader
        title="Vegas Intelligence"
        description={`Track line movement, implied totals, betting trends, and AI market analysis.${slateDescription}`}
        actions={<VegasHeaderActions generatedAt={report.generated_at} providerName={sampleVegas?.provider_name ?? null} isMock={sampleVegas?.is_mock ?? false} />}
      />
      <VegasIntelligenceBoard report={report} rows={rows} history={history} coverage={coverage} />
    </div>
  );
}
