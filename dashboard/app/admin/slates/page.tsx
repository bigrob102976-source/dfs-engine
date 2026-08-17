import Link from "next/link";

import { StatusCard } from "@/components/StatusCard";
import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";

export const dynamic = "force-dynamic";

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
    </div>
  );
}
