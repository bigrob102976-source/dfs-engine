import Link from "next/link";

import { AdminSlateOperations } from "@/components/admin/AdminSlateOperations";
import { SlateDateSelector } from "@/components/admin/SlateDateSelector";
import { StatusCard } from "@/components/StatusCard";
import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildDkSlateVegasCoverage } from "@/lib/dkVegasCoverage";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { loadLatestDkMatchReport } from "@/lib/loaders";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";
import { resolveSlateDate } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleString();
}

/** Milestone 29: the production Slate Operations page -- ADMIN-only
 * (gated by app/admin/layout.tsx's requireAdmin()). Pipeline health for
 * today's date at the top (reuses the exact same buildPipelineStatuses/
 * buildSlateSummary/StatusCard the rest of the dashboard uses, so it can
 * never drift into showing a fabricated or differently-computed status),
 * then the real per-slate Slate Operations board below (Upload/Process/
 * Refresh/Publish/Unpublish/Archive -- components/admin/AdminSlateOperations.tsx),
 * each action server-side-gated by its own /api/admin/slates/* route's
 * requireAdminApi() call. This is now the ONLY place these actions live
 * -- the member dashboard's Slate Manager (/dashboard/slates) is a
 * read-only status view with no upload/refresh/publish controls. */
export default async function AdminSlatesPage(props: PageProps<"/admin/slates">) {
  const searchParams = await props.searchParams;
  const dateParam = typeof searchParams.date === "string" ? searchParams.date : undefined;
  const dateResolution = resolveSlateDate(dateParam);
  // An invalid explicit ?date= falls back to today rather than showing a
  // hard error on a whole-page navigation -- the date input itself only
  // ever produces valid YYYY-MM-DD values, so this only guards a
  // hand-edited URL.
  const date = dateResolution.ok ? dateResolution.date : getTodayChicagoDate();
  const [summary, statuses, environmentReport, matchReportLoaded, environmentStatus] = await Promise.all([
    buildSlateSummary(date),
    buildPipelineStatuses(date),
    loadLatestEnvironmentReport(date),
    loadLatestDkMatchReport(date),
    getGameEnvironmentStatus(date),
  ]);
  const matchReport = matchReportLoaded.data;
  const vegasCoverage = buildDkSlateVegasCoverage(matchReport, environmentReport);
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

      <SlateDateSelector date={date} basePath="/admin/slates" />

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

      <div className="mt-4">
        <AdminSlateOperations date={date} />
      </div>
    </div>
  );
}
