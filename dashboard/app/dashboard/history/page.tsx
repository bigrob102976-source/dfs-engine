import { SimpleBarChart } from "@/components/SimpleBarChart";
import { buildHistorySeries } from "@/lib/history";

export const dynamic = "force-dynamic";

export default function HistoryPage() {
  const series = buildHistorySeries();

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">History</h1>
      <p className="mb-4 text-xs text-text-faint">
        {series.length > 0 ? `${series.length} slate(s) with saved artifacts.` : "No artifacts found yet."}
      </p>

      {series.length === 0 ? (
        <div className="rounded border border-border bg-bg-panel p-6 text-sm text-text-faint">
          Nothing to chart yet -- build a research package for at least one slate first.
        </div>
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

      <div className="mt-4 rounded-lg border border-border bg-bg-panel p-4 text-xs text-text-faint">
        <span className="font-semibold text-text-muted">Optimizer Runtime:</span> not tracked yet -- no lineup-set
        artifact currently records solve duration. Would require adding a timing field to
        optimizer/persistence.py&apos;s saved document rather than being invented here.
      </div>
    </div>
  );
}
