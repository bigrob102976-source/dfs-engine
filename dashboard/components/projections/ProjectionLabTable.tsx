"use client";

import { useMemo, useState } from "react";

import { POSITION_TABS, type PositionTab } from "@/lib/dkRosterRules";
import type { ProjectionLabRow } from "@/lib/projectionLab";
import { formatDelta, formatProjectionCell } from "@/lib/projectionLabels";
import { sortRows, type SortDirection } from "@/lib/sortFilter";

interface Column {
  key: keyof ProjectionLabRow | "delta1" | "delta2";
  label: string;
  sortKey?: keyof ProjectionLabRow;
  align?: "left" | "right";
}

const COLUMNS: Column[] = [
  { key: "position", label: "Pos" },
  { key: "name", label: "Player", sortKey: "name" },
  { key: "team", label: "Team", sortKey: "team" },
  { key: "salary", label: "Salary", sortKey: "salary", align: "right" },
  { key: "blueCollarProjection", label: "BlueCollar", sortKey: "blueCollarProjection", align: "right" },
  { key: "nativeProjection", label: "Big Money Native", sortKey: "nativeProjection", align: "right" },
  { key: "aiProjection", label: "Big Money AI", sortKey: "aiProjection", align: "right" },
  { key: "fantasyProsProjection", label: "FantasyPros", sortKey: "fantasyProsProjection", align: "right" },
  { key: "mlProjection", label: "Big Money ML", sortKey: "mlProjection", align: "right" },
  { key: "aiVsNativeDelta", label: "AI Δ", sortKey: "aiVsNativeDelta", align: "right" },
  { key: "bigMoneyVsBlueCollarDelta", label: "BM vs BC Δ", sortKey: "bigMoneyVsBlueCollarDelta", align: "right" },
  { key: "fpVsNativeDelta", label: "FP vs Native Δ", sortKey: "fpVsNativeDelta", align: "right" },
  { key: "fpVsAiDelta", label: "FP vs AI Δ", sortKey: "fpVsAiDelta", align: "right" },
  { key: "mlVsNativeDelta", label: "ML vs Native Δ", sortKey: "mlVsNativeDelta", align: "right" },
  { key: "mlVsAiDelta", label: "ML vs AI Δ", sortKey: "mlVsAiDelta", align: "right" },
  { key: "mlVsFantasyProsDelta", label: "ML vs FP Δ", sortKey: "mlVsFantasyProsDelta", align: "right" },
  { key: "ownership", label: "Own%", sortKey: "ownership", align: "right" },
  { key: "leverage", label: "Lev", sortKey: "leverage", align: "right" },
  { key: "actualDkPoints", label: "Actual DK", sortKey: "actualDkPoints", align: "right" },
];

/** PROJECTION LAB main table (Milestone 27): the dedicated side-by-side
 * comparison the milestone asks for -- BlueCollar / Big Money Native /
 * Big Money AI / deltas / Actual DK, all in one row per player. Purely a
 * presentation + client-side filter/sort layer over rows the SERVER
 * page already built (lib/projectionLab.ts) -- never recomputes a
 * projection. */
export function ProjectionLabTable({ rows }: { rows: ProjectionLabRow[] }) {
  const [positionTab, setPositionTab] = useState<PositionTab>("ALL");
  const [team, setTeam] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof ProjectionLabRow>("nativeProjection");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const teams = useMemo(() => Array.from(new Set(rows.map((r) => r.team))).sort(), [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (positionTab === "P" && r.playerType !== "pitcher") return false;
      if (positionTab !== "ALL" && positionTab !== "P" && r.position !== positionTab) return false;
      if (team !== "ALL" && r.team !== team) return false;
      if (q && !r.name.toLowerCase().includes(q) && !r.team.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [rows, positionTab, team, search]);

  const sorted = useMemo(() => sortRows(filtered, sortKey, sortDir), [filtered, sortKey, sortDir]);

  function handleSort(key: keyof ProjectionLabRow) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {POSITION_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setPositionTab(tab)}
              className={`rounded px-2 py-1 text-xs font-medium uppercase tracking-wide ${
                positionTab === tab ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-faint hover:text-text-muted"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <select
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          aria-label="Team"
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
        >
          <option value="ALL">All Teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search players..."
          className="ml-auto w-56 rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none placeholder:text-text-faint focus:border-accent"
        />
        <span className="text-[11px] text-text-faint">{sorted.length} players</span>
      </div>

      <div className="max-h-[640px] overflow-auto rounded-[var(--radius-control)] border border-border">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg-panel-raised">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  onClick={col.sortKey ? () => handleSort(col.sortKey!) : undefined}
                  className={`whitespace-nowrap px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-text-faint ${col.align === "right" ? "text-right" : ""} ${col.sortKey ? "cursor-pointer select-none hover:text-text-muted" : ""}`}
                >
                  {col.label}
                  {col.sortKey === sortKey ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-2 py-6 text-center text-text-faint">
                  No players match the current filters.
                </td>
              </tr>
            )}
            {sorted.map((r) => (
              <tr key={r.id} className="border-t border-border-subtle/60 text-text-muted">
                <td className="px-2 py-1 text-text-muted">{r.playerType === "pitcher" ? "P" : (r.position ?? "--")}</td>
                <td className="px-2 py-1 font-medium text-text">{r.name}</td>
                <td className="px-2 py-1">{r.team}</td>
                <td className="px-2 py-1 text-right">{r.salary !== null ? `$${r.salary.toLocaleString()}` : "--"}</td>
                <td className="px-2 py-1 text-right">{formatProjectionCell(r.blueCollarProjection, "NOT AVAILABLE")}</td>
                <td className="px-2 py-1 text-right text-purple">{formatProjectionCell(r.nativeProjection)}</td>
                <td className="px-2 py-1 text-right text-purple">{formatProjectionCell(r.aiProjection)}</td>
                <td className="px-2 py-1 text-right">{formatProjectionCell(r.fantasyProsProjection, "NOT AVAILABLE")}</td>
                <td className="px-2 py-1 text-right text-purple">{formatProjectionCell(r.mlProjection, "NOT AVAILABLE")}</td>
                <td className={`px-2 py-1 text-right ${r.aiVsNativeDelta !== null && r.aiVsNativeDelta >= 0 ? "text-green" : r.aiVsNativeDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.aiVsNativeDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.bigMoneyVsBlueCollarDelta !== null && r.bigMoneyVsBlueCollarDelta >= 0 ? "text-green" : r.bigMoneyVsBlueCollarDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.bigMoneyVsBlueCollarDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.fpVsNativeDelta !== null && r.fpVsNativeDelta >= 0 ? "text-green" : r.fpVsNativeDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.fpVsNativeDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.fpVsAiDelta !== null && r.fpVsAiDelta >= 0 ? "text-green" : r.fpVsAiDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.fpVsAiDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.mlVsNativeDelta !== null && r.mlVsNativeDelta >= 0 ? "text-green" : r.mlVsNativeDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.mlVsNativeDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.mlVsAiDelta !== null && r.mlVsAiDelta >= 0 ? "text-green" : r.mlVsAiDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.mlVsAiDelta)}
                </td>
                <td className={`px-2 py-1 text-right ${r.mlVsFantasyProsDelta !== null && r.mlVsFantasyProsDelta >= 0 ? "text-green" : r.mlVsFantasyProsDelta !== null ? "text-red" : ""}`}>
                  {formatDelta(r.mlVsFantasyProsDelta)}
                </td>
                <td className="px-2 py-1 text-right">{r.ownership !== null ? `${r.ownership.toFixed(1)}%` : "--"}</td>
                <td className="px-2 py-1 text-right">{formatProjectionCell(r.leverage)}</td>
                <td className="px-2 py-1 text-right font-semibold text-text">{r.actualDkPoints === null ? "--" : r.actualDkPoints.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
