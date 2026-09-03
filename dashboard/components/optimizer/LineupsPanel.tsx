"use client";

import { Fragment, useMemo, useState } from "react";

import { buildExposureRows, buildStackExposureRows } from "@/lib/optimizerWorkspace/exposureSummary";
import type { OptimizerBuildResult } from "@/lib/optimizerWorkspace/types";
import type { Lineup } from "@/lib/types";

const SLOT_ORDER = ["P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF"];
const PAGE_SIZE = 25;

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "--" : v.toFixed(digits);
}

function ExpandedLineup({ lineup }: { lineup: Lineup }) {
  return (
    <div className="border-t border-border-subtle bg-bg p-3">
      <table className="w-full text-xs">
        <tbody>
          {lineup.assignments.map((a, i) => (
            <tr key={i} className="border-b border-border-subtle last:border-0">
              <td className="w-10 py-1 font-mono text-text-faint">{SLOT_ORDER[i] ?? a.slot}</td>
              <td className="py-1 text-text">{a.name}</td>
              <td className="py-1 text-text-muted">{a.team}</td>
              <td className="py-1 text-text-muted">{a.opponent ?? "--"}</td>
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

function ExposureTable({ title, rows }: { title: string; rows: Array<{ label: string; sub?: string; lineups: number; exposurePercent: number }> }) {
  if (rows.length === 0) return null;
  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text-faint">
            <th className="pb-1 text-left">Player</th>
            <th className="pb-1 text-right">Lineups</th>
            <th className="pb-1 text-right">Exposure</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-border-subtle">
              <td className="py-1 text-text">
                {r.label} {r.sub && <span className="text-text-faint">({r.sub})</span>}
              </td>
              <td className="py-1 text-right text-text-muted">{r.lineups}</td>
              <td className="py-1 text-right text-text-muted">{r.exposurePercent}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Generated lineups table (click a row to expand its roster), plus
 * player/pitcher/team-stack exposure summaries and a CSV export button.
 * A plain paginated table (PAGE_SIZE=25) instead of a virtualization
 * library keeps up to 150 lineups responsive without adding a new
 * dependency -- only the current page's rows are ever mounted. */
export function LineupsPanel({ result }: { result: OptimizerBuildResult }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [page, setPage] = useState(0);

  const pageCount = Math.max(1, Math.ceil(result.lineups.length / PAGE_SIZE));
  const pageLineups = result.lineups.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const playerExposure = useMemo(() => buildExposureRows(result.lineups), [result.lineups]);
  const pitcherExposure = useMemo(() => buildExposureRows(result.lineups, "pitcher"), [result.lineups]);
  const stackExposure = useMemo(() => buildStackExposureRows(result.lineups), [result.lineups]);

  if (result.lineups.length === 0) {
    return <div className="rounded border border-border bg-bg-panel p-4 text-xs text-text-faint">No lineups were generated.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-faint">
        <span>
          Generated <span className="text-text">{result.lineupsGenerated}</span> / {result.lineupsRequested} lineup(s) in{" "}
          {(result.elapsedMs / 1000).toFixed(1)}s
          {result.stoppedReason && <span className="text-yellow"> -- {result.stoppedReason}</span>}
        </span>
        {result.lineupSetPath && (
          <a
            href={`/api/optimizer/export?path=${encodeURIComponent(result.csvPath ?? "")}`}
            className="rounded border border-accent bg-accent-dim px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-text"
            download
          >
            Export Lineups (CSV)
          </a>
        )}
      </div>

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-bg-panel-raised text-text-faint">
              <th className="px-2 py-1.5 text-left">#</th>
              <th className="px-2 py-1.5 text-right">Salary</th>
              <th className="px-2 py-1.5 text-right">Remaining</th>
              <th className="px-2 py-1.5 text-right">Projection</th>
              <th className="px-2 py-1.5 text-right">Ceiling</th>
              <th className="px-2 py-1.5 text-right">Own Sum</th>
              <th className="px-2 py-1.5 text-right">Avg Risk</th>
              <th className="px-2 py-1.5 text-right">Avg Conf</th>
              <th className="px-2 py-1.5 text-left">Primary Stack</th>
            </tr>
          </thead>
          <tbody>
            {pageLineups.map((lineup) => (
              <Fragment key={lineup.index}>
                <tr
                  onClick={() => setExpanded(expanded === lineup.index ? null : lineup.index)}
                  className="cursor-pointer border-b border-border-subtle hover:bg-bg-panel-raised"
                >
                  <td className="px-2 py-1.5 text-text">{lineup.index}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">${lineup.salary}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">${lineup.remaining_salary}</td>
                  <td className="px-2 py-1.5 text-right text-text">{fmt(lineup.projection)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.ceiling)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{lineup.sum_ownership !== null ? `${fmt(lineup.sum_ownership)}%` : "--"}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.average_risk)}</td>
                  <td className="px-2 py-1.5 text-right text-text-muted">{fmt(lineup.average_confidence)}</td>
                  <td className="px-2 py-1.5 text-text-muted">
                    {lineup.primary_stack_team ? `${lineup.primary_stack_team} (${lineup.primary_stack_size})` : "--"}
                  </td>
                </tr>
                {expanded === lineup.index && (
                  <tr>
                    <td colSpan={9} className="p-0">
                      <ExpandedLineup lineup={lineup} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded bg-bg-panel-raised px-2 py-1 text-text-muted disabled:opacity-30"
          >
            Prev
          </button>
          <span className="text-text-faint">
            Page {page + 1} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
            className="rounded bg-bg-panel-raised px-2 py-1 text-text-muted disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <ExposureTable title="Player Exposure" rows={playerExposure.map((r) => ({ label: r.name, sub: r.team, lineups: r.lineups, exposurePercent: r.exposurePercent }))} />
        <ExposureTable title="Pitcher Exposure" rows={pitcherExposure.map((r) => ({ label: r.name, sub: r.team, lineups: r.lineups, exposurePercent: r.exposurePercent }))} />
        <ExposureTable title="Team Stack Exposure" rows={stackExposure.map((r) => ({ label: r.team, lineups: r.lineups, exposurePercent: r.exposurePercent }))} />
      </div>
    </div>
  );
}
