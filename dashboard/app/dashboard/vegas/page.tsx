import { VegasHeaderActions } from "@/components/vegas/VegasHeaderActions";
import { VegasIntelligenceBoard } from "@/components/vegas/VegasIntelligenceBoard";
import { GenerateEnvironmentButton } from "@/components/environment/GenerateEnvironmentButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildVegasGameRows } from "@/lib/vegasIntelligence";

export const dynamic = "force-dynamic";

/** Vegas Intelligence Board (Milestone DS3): line movement, implied
 * totals, betting trends, and deterministic AI market analysis for
 * today's slate. Reads the same immutable Game Environment snapshot the
 * /dashboard/environment terminal reads (Milestone DS2) -- Vegas data
 * has always lived inside that report, this page is just its dedicated,
 * premium home. Never computes odds, never touches Projections,
 * Ownership, or the Optimizer. */
export default async function VegasPage() {
  const date = getTodayChicagoDate();
  const report = loadLatestEnvironmentReport(date);
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
          title="No Vegas Data"
          description="Today's Game Environment report has games, but none have Vegas odds yet. Regenerate the report to try again."
          action={<GenerateEnvironmentButton />}
        />
      </div>
    );
  }

  const pitcherSnapshot = loadLatestPitcherSnapshot(date).data;
  const rows = buildVegasGameRows(report.games, pitcherSnapshot?.pitchers ?? []);
  const sampleVegas = gamesWithVegas[0]?.vegas ?? null;

  return (
    <div>
      <PageHeader
        title="Vegas Intelligence"
        description="Track line movement, implied totals, betting trends, and AI market analysis."
        actions={<VegasHeaderActions generatedAt={report.generated_at} providerName={sampleVegas?.provider_name ?? null} isMock={sampleVegas?.is_mock ?? false} />}
      />
      <VegasIntelligenceBoard report={report} rows={rows} />
    </div>
  );
}
