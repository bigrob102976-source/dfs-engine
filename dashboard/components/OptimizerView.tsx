"use client";

import { Fragment, useState } from "react";

import type { Lineup, LineupSet } from "@/lib/types";

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "--" : v.toFixed(digits);
}

const SLOT_ORDER = ["P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF"];

function ExpandedLineup({ lineup }: { lineup: Lineup }) {
  // Assignments already come out of the solver in P,P,C,1B,2B,3B,SS,OF,OF,OF
  // order (see optimizer/solver.py's expand_slot_instances) -- display as-is,
  // falling back to a stable resort if that ever changes.
  const bySlotOrder = [...lineup.assignments];
  return (
    <div className="border-t border-border-subtle bg-bg p-3">
      <table className="w-full text-xs">
        <tbody>
          {bySlotOrder.map((a, i) => (
            <tr key={i} className="border-b border-border-subtle last:border-0">
              <td className="w-10 py-1 font-mono text-text-faint">{SLOT_ORDER[i] ?? a.slot}</td>
              <td className="py-1 text-text">{a.name}</td>
              <td className="py-1 text-text-muted">{a.team}</td>
              <td className="py-1 text-right text-text-muted">${a.salary}</td>
              <td className="py-1 text-right text-text-muted">{fmt(a.projection)}</td>
              <td className="py-1 text-right text-text-muted">{a.projected_ownership !== null ? `${fmt(a.projected_ownership)}%` : "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OptimizerView({ runs }: { runs: Array<{ filename: string; data: LineupSet }> }) {
  const [selectedRun, setSelectedRun] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);

  if (runs.length === 0) return null;
  const run = runs[selectedRun].data;

  return (
    <div>
      {runs.length > 1 && (
        <div className="mb-3 flex gap-2">
          {runs.map((r, i) => (
            <button
              key={r.filename}
              onClick={() => {
                setSelectedRun(i);
                setExpanded(null);
              }}
              className={`rounded px-3 py-1 text-xs ${
                i === selectedRun ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-muted hover:text-text"
              }`}
            >
              {r.data.settings?.objective_mode ?? "run"} &middot; {r.filename.replace("dk_lineups_", "").replace(".json", "")}
            </button>
          ))}
        </div>
      )}

      <div className="mb-3 text-xs text-text-faint">
        Objective: <span className="text-text-muted">{String(run.settings?.objective_mode ?? "unknown")}</span> &middot; Generated{" "}
        {run.lineups_generated} / {run.lineups_requested}
        {run.stopped_reason && <span className="text-yellow"> &middot; {run.stopped_reason}</span>}
      </div>

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-bg-panel-raised text-text-faint">
              <th className="px-2 py-1.5 text-left">#</th>
              <th className="px-2 py-1.5 text-right">Projection</th>
              <th className="px-2 py-1.5 text-right">Ceiling</th>
              <th className="px-2 py-1.5 text-right">Salary</th>
              <th className="px-2 py-1.5 text-right">Ownership Sum</th>
              <th className="px-2 py-1.5 text-left">Primary Stack</th>
              <th className="px-2 py-1.5 text-right">Avg Confidence</th>
              <th className="px-2 py-1.5 text-right">Avg Risk</th>
            </tr>
          </thead>
          <tbody>
            {run.lineups.map((lineup) => (
              <Fragment key={lineup.index}>
                <tr
                  onClick={() => setExpanded(expanded === lineup.index ? null : lineup.index)}
                  className="cursor-pointer border-b border-border-subtle hover:bg-bg-panel-raised"
                >
                  <td className="px-2 py-1.5 text-text">{lineup.index}</td>
                  <td className="px-2 py-1.5 text-right text-text">{fmt(lineup.projection)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.ceiling)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">${lineup.salary}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">
                    {lineup.sum_ownership !== null ? `${fmt(lineup.sum_ownership)}%` : "--"}
                  </td>
                  <td className="px-2 py-1.5 text-text-muted">
                    {lineup.primary_stack_team ? `${lineup.primary_stack_team} (${lineup.primary_stack_size})` : "--"}
                  </td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.average_confidence)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.average_risk)}</td>
                </tr>
                {expanded === lineup.index && (
                  <tr>
                    <td colSpan={8} className="p-0">
                      <ExpandedLineup lineup={lineup} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
