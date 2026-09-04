import { PageHeader } from "@/components/ui/Header";
import { getTodayEasternDate } from "@/lib/currentDate";
import { qualityReportToRows, ratioHealth, type CompletenessRow, type HealthColor } from "@/lib/health";
import { loadLatestBatterSnapshot, loadLatestDkMatchReport, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

const DOT: Record<HealthColor, string> = { green: "bg-green", yellow: "bg-yellow", red: "bg-red", gray: "bg-text-faint" };

function Row({ row }: { row: CompletenessRow }) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
      <span className="flex items-center gap-2 text-sm text-text">
        <span className={`h-2 w-2 rounded-full ${DOT[row.color]}`} />
        {row.label}
      </span>
      <span className="text-sm text-text-muted">
        {row.count} / {row.total}
      </span>
    </div>
  );
}

function NotImplementedRow({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
      <span className="flex items-center gap-2 text-sm text-text">
        <span className="h-2 w-2 rounded-full bg-text-faint" />
        {label}
      </span>
      <span className="text-sm text-text-faint">Not Implemented</span>
    </div>
  );
}

export default async function ModelHealthPage(props: PageProps<"/dashboard/health">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayEasternDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const [pitcherLoaded, batterLoaded, ownershipLoaded, matchReportLoaded] = await Promise.all([
    date ? loadLatestPitcherSnapshot(date) : null,
    date ? loadLatestBatterSnapshot(date) : null,
    date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null) : null,
    date ? loadLatestDkMatchReport(date, slateCtx.selected?.slateId ?? null) : null,
  ]);
  const pitcherSnapshot = pitcherLoaded?.data ?? null;
  const batterSnapshot = batterLoaded?.data ?? null;
  const ownership = ownershipLoaded?.data ?? null;
  const matchReport = matchReportLoaded?.data ?? null;
  const slateDescription = slateCtx.selected ? ` -- ${formatSlateLabel(slateCtx.selected)}` : "";

  const pitcherTotal = pitcherSnapshot?.pitcher_count ?? 0;
  const hitterTotal = batterSnapshot?.hitter_count ?? 0;

  const pitcherRows = qualityReportToRows(pitcherSnapshot?.research_quality_report as { counts?: Record<string, number> }, pitcherTotal);
  const hitterRows = qualityReportToRows(batterSnapshot?.research_quality_report as { counts?: Record<string, number> }, hitterTotal);

  const ownershipCount = ownership?.players.length ?? 0;
  const expectedOwnership = pitcherTotal + hitterTotal;

  const salaryCoverage = typeof matchReport?.salary_coverage_percent === "number" ? (matchReport.salary_coverage_percent as number) : null;

  return (
    <div>
      <PageHeader
        title="Model Health"
        description={
          date
            ? `Completeness for slate ${date}, read directly from the Research Quality Report already computed by the Python pipeline.${slateDescription}`
            : "No slate loaded yet."
        }
      />

      {date && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
              Pitchers ({pitcherTotal})
            </div>
            {pitcherRows.length === 0 ? (
              <div className="p-3 text-xs text-text-faint">Pitcher snapshot not generated yet.</div>
            ) : (
              pitcherRows.map((r) => <Row key={r.label} row={r} />)
            )}
          </div>

          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
              Hitters ({hitterTotal})
            </div>
            {hitterRows.length === 0 ? (
              <div className="p-3 text-xs text-text-faint">Batter snapshot not generated yet.</div>
            ) : (
              hitterRows.map((r) => <Row key={r.label} row={r} />)
            )}
          </div>

          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
              Other Coverage
            </div>
            <Row row={{ label: "Ownership", count: ownershipCount, total: expectedOwnership, color: ratioHealth(ownershipCount, expectedOwnership) }} />
            {salaryCoverage !== null ? (
              <Row row={{ label: "Salary", count: Math.round(salaryCoverage), total: 100, color: ratioHealth(salaryCoverage, 100) }} />
            ) : (
              <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
                <span className="text-sm text-text">Salary</span>
                <span className="text-sm text-text-faint">no DK import yet</span>
              </div>
            )}
            <Row
              row={{
                label: "Missing Lineups",
                count: batterSnapshot?.missing_lineup_game_ids?.length ?? 0,
                total: 0,
                color: (batterSnapshot?.missing_lineup_game_ids?.length ?? 0) > 0 ? "yellow" : "green",
              }}
            />
          </div>

          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
              Not Yet Built
            </div>
            <NotImplementedRow label="Weather" />
            <NotImplementedRow label="Vegas" />
            <NotImplementedRow label="Umpire" />
          </div>
        </div>
      )}
    </div>
  );
}
