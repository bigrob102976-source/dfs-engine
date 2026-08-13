"use client";

import { useMemo, useState } from "react";

import { POSITION_TABS, type PositionTab } from "@/lib/dkRosterRules";
import { sortRows, type SortDirection } from "@/lib/sortFilter";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

interface Column {
  key: string;
  label: string;
  sortKey?: keyof PoolPlayerRow;
  align?: "left" | "right";
}

const COLUMNS: Column[] = [
  { key: "lock", label: "Lock" },
  { key: "exclude", label: "Exclude" },
  { key: "position", label: "Pos" },
  { key: "name", label: "Name", sortKey: "name" },
  { key: "team", label: "Team", sortKey: "team" },
  { key: "opponent", label: "Opp", sortKey: "opponent" },
  { key: "battingOrder", label: "Ord", sortKey: "battingOrder", align: "right" },
  { key: "salary", label: "Salary", sortKey: "salary", align: "right" },
  { key: "projection", label: "Proj", sortKey: "projection", align: "right" },
  { key: "ceiling", label: "Ceil", sortKey: "ceiling", align: "right" },
  { key: "value", label: "Value", sortKey: "value", align: "right" },
  { key: "ownership", label: "Own%", sortKey: "ownership", align: "right" },
  { key: "leverage", label: "Lev", sortKey: "leverage", align: "right" },
  { key: "risk", label: "Risk", sortKey: "risk", align: "right" },
  { key: "confidence", label: "Conf", sortKey: "confidence", align: "right" },
  { key: "exposure", label: "Exposure" },
];

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

export function PoolTable({
  players,
  locks,
  exclusions,
  maxExposure,
  onToggleLock,
  onToggleExclude,
  onExposureChange,
}: {
  players: PoolPlayerRow[];
  locks: Set<string>;
  exclusions: Set<string>;
  maxExposure: Record<string, number>;
  onToggleLock: (dkPlayerId: string) => void;
  onToggleExclude: (dkPlayerId: string) => void;
  onExposureChange: (dkPlayerId: string, fraction: number) => void;
}) {
  const [positionTab, setPositionTab] = useState<PositionTab>("ALL");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof PoolPlayerRow>("projection");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return players.filter((p) => {
      if (positionTab === "P" && p.playerType !== "pitcher") return false;
      if (positionTab !== "ALL" && positionTab !== "P" && !p.positions.includes(positionTab)) return false;
      if (q && !p.name.toLowerCase().includes(q) && !p.team.toLowerCase().includes(q) && !(p.opponent ?? "").toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [players, positionTab, search]);

  const sorted = useMemo(() => sortRows(filtered, sortKey, sortDir), [filtered, sortKey, sortDir]);

  function handleSort(key: keyof PoolPlayerRow) {
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
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search players..."
          className="ml-auto w-56 rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none placeholder:text-text-faint focus:border-accent"
        />
        <span className="text-[11px] text-text-faint">{sorted.length} players</span>
      </div>

      <div className="max-h-[560px] overflow-auto rounded border border-border">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg-panel-raised">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  onClick={col.sortKey ? () => handleSort(col.sortKey!) : undefined}
                  className={`border-b border-border px-2 py-1.5 text-[11px] uppercase tracking-wide text-text-faint ${
                    col.align === "right" ? "text-right" : "text-left"
                  } ${col.sortKey ? "cursor-pointer select-none hover:text-text-muted" : ""}`}
                >
                  {col.label}
                  {col.sortKey === sortKey ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => {
              const isLocked = locks.has(p.dkPlayerId);
              const isExcluded = exclusions.has(p.dkPlayerId);
              const exposurePercent = Math.round((maxExposure[p.dkPlayerId] ?? 1) * 100);
              return (
                <tr
                  key={p.dkPlayerId}
                  className={`border-b border-border-subtle ${
                    isLocked ? "bg-accent-dim/30" : isExcluded ? "bg-red/10" : "hover:bg-bg-panel-raised"
                  }`}
                >
                  <td className="px-2 py-1">
                    <button
                      type="button"
                      onClick={() => onToggleLock(p.dkPlayerId)}
                      disabled={isExcluded}
                      aria-label={isLocked ? `Unlock ${p.name}` : `Lock ${p.name}`}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        isLocked ? "bg-green text-bg" : "bg-bg-panel-raised text-text-faint hover:text-text"
                      } disabled:cursor-not-allowed disabled:opacity-40`}
                    >
                      {isLocked ? "Locked" : "Lock"}
                    </button>
                  </td>
                  <td className="px-2 py-1">
                    <button
                      type="button"
                      onClick={() => onToggleExclude(p.dkPlayerId)}
                      disabled={isLocked}
                      aria-label={isExcluded ? `Restore ${p.name}` : `Exclude ${p.name}`}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        isExcluded ? "bg-red text-bg" : "bg-bg-panel-raised text-text-faint hover:text-text"
                      } disabled:cursor-not-allowed disabled:opacity-40`}
                    >
                      {isExcluded ? "Excluded" : "Exclude"}
                    </button>
                  </td>
                  <td className="px-2 py-1 text-text-muted">{p.playerType === "pitcher" ? "P" : p.positions.join("/")}</td>
                  <td className="px-2 py-1 font-medium text-text">{p.name}</td>
                  <td className="px-2 py-1 text-text-muted">{p.team}</td>
                  <td className="px-2 py-1 text-text-muted">{p.opponent ?? "--"}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{p.playerType === "pitcher" ? "" : (p.battingOrder ?? "--")}</td>
                  <td className="px-2 py-1 text-right text-text">${p.salary.toLocaleString()}</td>
                  <td className="px-2 py-1 text-right text-text">{fmt(p.projection)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.ceiling)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.value, 2)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{p.ownership !== null ? `${fmt(p.ownership)}%` : "--"}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.leverage)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.risk)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.confidence)}</td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={5}
                      value={exposurePercent}
                      disabled={isLocked || isExcluded}
                      onChange={(e) => {
                        const pct = Number(e.target.value);
                        if (Number.isFinite(pct)) onExposureChange(p.dkPlayerId, Math.min(100, Math.max(0, pct)) / 100);
                      }}
                      className="w-14 rounded border border-border bg-bg-panel-raised px-1 py-0.5 text-right text-text outline-none focus:border-accent disabled:opacity-40"
                    />
                    <span className="ml-0.5 text-text-faint">%</span>
                  </td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-2 py-6 text-center text-text-faint">
                  No players match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
