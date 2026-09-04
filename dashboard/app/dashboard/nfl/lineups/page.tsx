"use client";

import { useState } from "react";

import { DataCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NFL_ROSTER_SLOT_ORDER } from "@/lib/nfl/types";
import { fmtSalary, fmt } from "@/lib/nfl/format";
import { loadOptimizeResult } from "@/lib/nfl/optimizeResultStorage";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function LineupsContent() {
  const draftGroupId = useNflDraftGroupId();
  const [result] = useState(() => loadOptimizeResult(draftGroupId));

  if (!result) {
    return (
      <p className="text-sm text-text-faint">
        No lineups built yet for this slate. Go to the Optimizer tab, set Lock/Exclude and lineup count, then Build Lineups.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted">
        Generated {result.generated} / {result.requested} lineup(s) -- mode: {result.mode}
        {result.stopped_reason && <span className="ml-2 text-yellow">{result.stopped_reason}</span>}
      </p>
      {result.lineups.map((lineup) => (
        <DataCard key={lineup.index} title={`Lineup ${lineup.index + 1}`}>
          <div className="mb-2 flex flex-wrap gap-4 text-xs text-text-muted">
            <span>
              Total Salary: <span className="font-semibold text-text">{fmtSalary(lineup.total_salary)}</span>
            </span>
            <span>
              Remaining Salary: <span className="font-semibold text-text">{fmtSalary(lineup.remaining_salary)}</span>
            </span>
            {result.mode === "projection" && (
              <span>
                Total Projection: <span className="font-semibold text-text">{fmt(lineup.total_projection)}</span>
              </span>
            )}
          </div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-text-faint">
                <th className="py-1.5 pr-3 font-medium">Slot</th>
                <th className="py-1.5 pr-3 font-medium">Player</th>
                <th className="py-1.5 pr-3 font-medium">Team</th>
                <th className="py-1.5 pr-3 font-medium">Salary</th>
              </tr>
            </thead>
            <tbody>
              {NFL_ROSTER_SLOT_ORDER.map((slot) => {
                const a = lineup.assignments.find((x) => x.slot === slot);
                return (
                  <tr key={slot} className="border-b border-border-subtle/50">
                    <td className="py-1.5 pr-3 text-text-faint">{slot}</td>
                    <td className="py-1.5 pr-3 font-medium text-text">{a?.name ?? "--"}</td>
                    <td className="py-1.5 pr-3 text-text-muted">{a?.team ?? "--"}</td>
                    <td className="py-1.5 pr-3 text-text-muted">{a ? fmtSalary(a.salary) : "--"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DataCard>
      ))}
      <p className="text-[11px] text-text-faint">Ownership unavailable -- aggregate lineup ownership omitted until real ownership data exists (M12).</p>
    </div>
  );
}

export default function NflLineupsPage() {
  return (
    <NflPageShell title="NFL Lineups" description="Generated lineups from the real nfl/solver.py optimizer.">
      <LineupsContent />
    </NflPageShell>
  );
}
