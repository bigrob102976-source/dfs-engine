import { DataCard } from "@/components/ui/Card";
import type { TeamReadinessRow } from "@/lib/slateReadiness";

function Badge({ ok, okLabel, pendingLabel }: { ok: boolean; okLabel: string; pendingLabel: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${ok ? "bg-green/15 text-green" : "bg-text-faint/15 text-text-faint"}`}>
      {ok ? okLabel : pendingLabel}
    </span>
  );
}

/** M32.7: per-team operational readiness -- every column is a direct
 * read of already-computed state (eligibility, joined Native/AI/ML
 * rows, the BlueCollar snapshot, lib/stacks.ts's own per-team status).
 * Nothing here recomputes eligibility or a stack. */
export function TeamReadinessTable({ rows }: { rows: TeamReadinessRow[] }) {
  return (
    <DataCard title="Team Readiness">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-text-faint">
              <th className="px-1 py-1 text-left">Team</th>
              <th className="px-1 py-1 text-left">Lineup</th>
              <th className="px-1 py-1 text-left">Starter</th>
              <th className="px-1 py-1 text-left">BlueCollar</th>
              <th className="px-1 py-1 text-left">Native</th>
              <th className="px-1 py-1 text-left">AI</th>
              <th className="px-1 py-1 text-left">ML</th>
              <th className="px-1 py-1 text-left">Ownership</th>
              <th className="px-1 py-1 text-left">Stack</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.team} className="border-t border-border-subtle/60">
                <td className="px-1 py-1 font-semibold text-text">{r.team}</td>
                <td className="px-1 py-1"><Badge ok={r.lineupStatus === "CONFIRMED"} okLabel="Confirmed" pendingLabel="Unconfirmed" /></td>
                <td className="px-1 py-1"><Badge ok={r.starterStatus === "CONFIRMED"} okLabel="Confirmed" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.blueCollar === "AVAILABLE"} okLabel="Available" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.native === "GENERATED"} okLabel="Generated" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.ai === "GENERATED"} okLabel="Generated" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.ml === "GENERATED"} okLabel="Generated" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.ownership === "GENERATED"} okLabel="Generated" pendingLabel="Pending" /></td>
                <td className="px-1 py-1"><Badge ok={r.stackReady === "READY"} okLabel="Ready" pendingLabel="Waiting" /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="py-2 text-text-faint">No teams on this slate.</p>}
      </div>
    </DataCard>
  );
}
