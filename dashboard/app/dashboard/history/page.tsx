import { SimpleBarChart } from "@/components/SimpleBarChart";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { buildHistorySeries } from "@/lib/history";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const series = await buildHistorySeries();

  return (
    <div>
      <PageHeader title="History" description={series.length > 0 ? `${series.length} slate(s) with saved artifacts.` : undefined} />

      {series.length === 0 ? (
        <EmptyState icon="📉" title="Nothing to chart yet" description="Build a research package for at least one slate first." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SimpleBarChart title="Pitcher MAE by Slate" points={series.map((p) => ({ label: p.date, value: p.pitcherMae }))} />
          <SimpleBarChart title="Ownership MAE by Slate" points={series.map((p) => ({ label: p.date, value: p.ownershipMae }))} color="var(--yellow)" />
          <SimpleBarChart
            title="Projection Correlation"
            points={series.map((p) => ({ label: p.date, value: p.projectionCorrelation }))}
            color="var(--green)"
            digits={3}
          />
          <SimpleBarChart
            title="Ownership Correlation"
            points={series.map((p) => ({ label: p.date, value: p.ownershipCorrelation }))}
            color="var(--green)"
            digits={3}
          />
          <SimpleBarChart title="Number of Games" points={series.map((p) => ({ label: p.date, value: p.games }))} digits={0} />
          <SimpleBarChart
            title="Lineups Generated"
            points={series.map((p) => ({ label: p.date, value: p.lineupsGenerated }))}
            color="var(--accent)"
            digits={0}
          />
        </div>
      )}

      <div className="mt-4 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 text-xs text-text-faint shadow-[var(--shadow-card)]">
        <span className="font-semibold text-text-muted">Optimizer Runtime:</span> not tracked yet -- no lineup-set
        artifact currently records solve duration. Would require adding a timing field to
        optimizer/persistence.py&apos;s saved document rather than being invented here.
      </div>
    </div>
  );
}
