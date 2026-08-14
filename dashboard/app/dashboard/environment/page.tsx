import { EnvironmentTerminal } from "@/components/environment/EnvironmentTerminal";
import { GenerateEnvironmentButton } from "@/components/environment/GenerateEnvironmentButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestEnvironmentReport } from "@/lib/gameEnvironment";

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
 * ownership, or the optimizer. */
export default function EnvironmentPage() {
  const date = getTodayChicagoDate();
  const report = loadLatestEnvironmentReport(date);

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
        description={`${report.games.length} games · generated ${formatTimestamp(report.generated_at)} · engine v${report.engine_version}`}
        actions={<GenerateEnvironmentButton />}
      />
      <EnvironmentTerminal games={report.games} />
    </div>
  );
}
