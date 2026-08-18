import Link from "next/link";

import { StatusCard } from "@/components/StatusCard";
import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildDkSlateVegasCoverage } from "@/lib/dkVegasCoverage";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { loadLatestDkMatchReport } from "@/lib/loaders";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";

export const dynamic = "force-dynamic";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleString();
}

/** Read-only pipeline health for today's slate -- reuses the exact same
 * buildPipelineStatuses/buildSlateSummary/StatusCard the member-facing
 * Today's Slate page uses, so this can never drift into showing a
 * fabricated or differently-computed status. No destructive controls
 * live here; operational actions (refresh, generate lineups) stay on
 * the member dashboard where they already have safeguards. */
export default async function AdminSlatesPage() {
  const date = getTodayChicagoDate();
  const summary = buildSlateSummary(date);
  const statuses = buildPipelineStatuses(date);
  const environmentReport = loadLatestEnvironmentReport(date);
  const matchReport = loadLatestDkMatchReport(date).data;
  const vegasCoverage = buildDkSlateVegasCoverage(matchReport, environmentReport);
  const environmentStatus = await getGameEnvironmentStatus(date);
  const vegasProvider = "error" in environmentStatus ? null : environmentStatus.providers.vegas;

  return (
    <div>
      <PageHeader
        title="Slate Operations"
        description={`Pipeline health for ${date}, read directly from the same artifacts the member dashboard uses.`}
        actions={
          <Link href="/dashboard" className="text-xs text-accent hover:text-accent-hover">
            Open Today&apos;s Slate →
          </Link>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Games (Research)" value={summary.gamesOnResearch} />
        <MetricCard label="Games (DK Slate)" value={summary.gamesOnDkSlate ?? "--"} />
        <MetricCard label="Games With Lineups" value={summary.postedLineupGames} />
        <MetricCard label="Missing Lineup Games" value={summary.missingLineupGames} tone={summary.missingLineupGames > 0 ? "negative" : "neutral"} />
      </div>

      <DataCard title="Pipeline Stages">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {statuses.map((status) => (
            <StatusCard key={status.label} status={status} />
          ))}
        </div>
      </DataCard>

      <div className="mt-4">
        <DataCard title="Vegas Coverage">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">SportsGameOdds</div>
              <div className={`text-sm font-semibold ${vegasProvider && !vegasProvider.is_mock ? "text-green" : "text-text-faint"}`}>
                {vegasProvider ? (vegasProvider.is_mock ? "MOCK" : vegasProvider.source === "not_configured" ? "NOT CONNECTED" : "CONNECTED") : "UNKNOWN"}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">DK Slate Coverage</div>
              <div className="text-sm font-semibold text-text">{vegasCoverage.dkGames > 0 ? `${vegasCoverage.coveragePercent.toFixed(0)}%` : "--"}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">Last Pull</div>
              <div className="text-sm font-semibold text-text">{fmtDateTime(environmentReport?.generated_at ?? null)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">Pregame Games</div>
              <div className="text-sm font-semibold text-green">{vegasCoverage.pregameCovered}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">Frozen Games</div>
              <div className="text-sm font-semibold text-accent">{vegasCoverage.frozen}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">In-Play Ignored</div>
              <div className={`text-sm font-semibold ${vegasCoverage.inPlayIgnored > 0 ? "text-yellow" : "text-text"}`}>{vegasCoverage.inPlayIgnored}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-faint">Missing Games</div>
              <div className={`text-sm font-semibold ${vegasCoverage.missing > 0 ? "text-red" : "text-text"}`}>{vegasCoverage.missing}</div>
            </div>
          </div>
        </DataCard>
      </div>
    </div>
  );
}
