import { MetricCard } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadResearchSlate } from "@/lib/loaders";

export const dynamic = "force-dynamic";

/** Research Package overview: the raw counts and any data-quality notes
 * from today's research build. Pure read of research_output/ -- no
 * research/scoring logic lives here. */
export default function ResearchPage() {
  const date = getTodayChicagoDate();
  const slate = loadResearchSlate(date).data;

  return (
    <div>
      <PageHeader title="Research" description={slate ? `Research package for ${date}'s slate.` : undefined} />

      {!slate ? (
        <EmptyState
          icon="📊"
          title="Research is not ready for today's slate"
          description="Refresh today's slate from the main dashboard to build the research package."
        />
      ) : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Games" value={slate.counts.games} />
            <MetricCard label="Teams" value={slate.counts.teams} />
            <MetricCard label="Probable Pitchers" value={slate.counts.pitchers} />
            <MetricCard label="Posted Hitters" value={slate.counts.batters} />
          </div>

          {slate.notes.length > 0 ? (
            <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Data Quality Notes</h2>
              <ul className="list-inside list-disc text-xs text-text-muted">
                {slate.notes.map((n, i) => (
                  <li key={i} className="mb-0.5">
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-text-faint">No data-quality notes for this slate.</p>
          )}
        </>
      )}
    </div>
  );
}
