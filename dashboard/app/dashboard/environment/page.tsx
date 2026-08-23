import { EnvironmentTerminal } from "@/components/environment/EnvironmentTerminal";
import { GenerateEnvironmentButton } from "@/components/environment/GenerateEnvironmentButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";
import { effectiveGameIds, filterByGameIdField, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Game Environment research terminal (Milestone DS2): the Overall/
 * Hitter/Pitcher/Stack scores, Weather, Vegas, Bullpen, Park, Umpire, and
 * deterministic AI Summary research/game_environment/ builds for every
 * game on today's slate. Reads the latest immutable snapshot only -- this
 * page never computes scores itself and never touches projections,
 * ownership, or the optimizer.
 *
 * Milestone 32.6: filtered to the globally-selected slate's game_ids,
 * mirroring the Vegas page's already-established pattern exactly --
 * this page was the one slate-aware page that hadn't been wired up yet
 * (see GLOBAL SLATE CONTEXT). Full Day (the default) is unchanged. */
export default async function EnvironmentPage(props: PageProps<"/dashboard/environment">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const gameIds = effectiveGameIds(slateCtx);
  const fullDayReport = loadLatestEnvironmentReport(date);
  const report = fullDayReport ? { ...fullDayReport, games: filterByGameIdField(fullDayReport.games, gameIds) } : null;
  const slateDescription = slateCtx.selected ? ` -- ${formatSlateLabel(slateCtx.selected)}` : "";

  if (!report || report.games.length === 0) {
    return (
      <div>
        <PageHeader title="Game Environment" />
        <EmptyState
          icon="🌎"
          title="No Game Environment report yet for today's slate"
          description="Build a research package from the main dashboard first, then generate today's Game Environment report."
          action={<GenerateEnvironmentButton />}
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Game Environment"
        description={`${report.games.length} games · generated ${formatTimestamp(report.generated_at)} · engine v${report.engine_version}${slateDescription}`}
        actions={<GenerateEnvironmentButton />}
      />
      <EnvironmentTerminal games={report.games} />
    </div>
  );
}
