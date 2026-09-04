"use client";

import { useMemo, useState } from "react";

import { POSITION_TABS, type PositionTab } from "@/lib/dkRosterRules";
import { formatEligibilityStatus } from "@/lib/eligibilityLabels";
import { distinctValues, sortRows, type SortDirection } from "@/lib/sortFilter";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

import { PlayerDetailModal } from "./PlayerDetailModal";

// MLB WORKFLOW QA: a local extension of the shared POSITION_TABS (never
// modify that constant itself -- ProjectionLabTable.tsx renders it too,
// and its own filter treats every tab value as a literal DK position
// string; a "HIT" pseudo-tab there would always match zero rows). "P"
// (pitchers) already existed; "HIT" is the same idea for hitters,
// satisfying the "All / Pitchers / Hitters / Position" filter list.
type PoolTableTab = PositionTab | "HIT";
const POOL_TABLE_TABS: readonly PoolTableTab[] = ["ALL", "P", "HIT", ...POSITION_TABS.filter((t) => t !== "ALL" && t !== "P")];

type StarterFilter = "ALL" | "CONFIRMED" | "PROBABLE";
const ALL_TEAMS = "ALL_TEAMS";
const ALL_GAMES = "ALL_GAMES";

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
  { key: "eligibilityStatus", label: "Status", sortKey: "eligibilityStatus" },
  { key: "battingOrder", label: "Ord", sortKey: "battingOrder", align: "right" },
  { key: "salary", label: "Salary", sortKey: "salary", align: "right" },
  // MLB WORKFLOW QA: renamed from "Legacy" -- this is the primary
  // projection value the optimizer actually builds against (under
  // canonical Postgres serving it IS the Big Money Native value, see
  // canonicalPostgresBackend.ts's own "Native is the default projection
  // source, not a separate comparison column" docstring). "Legacy"
  // read as stale/deprecated to a real customer even though the number
  // is current; "BM Native"/"BM AI" alongside it remain the optional
  // admin-facing comparison columns, unchanged.
  { key: "projection", label: "Projection", sortKey: "projection", align: "right" },
  { key: "ceiling", label: "Ceil", sortKey: "ceiling", align: "right" },
  { key: "value", label: "Value", sortKey: "value", align: "right" },
  { key: "nativeProjection", label: "BM Native", sortKey: "nativeProjection", align: "right" },
  { key: "nativeDelta", label: "Native Δ", sortKey: "nativeDelta", align: "right" },
  { key: "ownership", label: "Own%", sortKey: "ownership", align: "right" },
  { key: "leverage", label: "Lev", sortKey: "leverage", align: "right" },
  { key: "risk", label: "Risk", sortKey: "risk", align: "right" },
  { key: "confidence", label: "Conf", sortKey: "confidence", align: "right" },
  { key: "exposure", label: "Exposure" },
];

// Milestone 17: optional projection comparison columns, spliced in
// right after "Proj" only when the caller (OptimizerWorkspace) has
// "Show comparison columns" checked.
const COMPARISON_COLUMNS: Column[] = [
  { key: "externalProjection", label: "BlueCollar", sortKey: "externalProjection", align: "right" },
  { key: "adjustedProjection", label: "BC Adj", sortKey: "adjustedProjection", align: "right" },
  { key: "adjustmentDelta", label: "BC Δ", sortKey: "adjustmentDelta", align: "right" },
];

// MLB V1 CUSTOMER DASHBOARD COMPLETION: Big Money AI has no real source
// under canonical Postgres serving (the production MLB backend) --
// poolPlayerRowFromCanonical() honestly leaves every ai* field null,
// never fabricated. Filling every row with "--" across 4 columns for a
// feature that structurally cannot ever have a value under the current
// serving backend reads as broken, not "unavailable" -- spliced in only
// when the pool itself reports real AI coverage (pool.hasAiProjections,
// the same real flag the Projection Source selector already uses),
// rather than hardcoding "always hidden": if AI data is ever wired up
// under canonical serving in a future milestone, these columns
// reappear automatically, with zero further change here.
const AI_COLUMNS: Column[] = [
  { key: "aiProjection", label: "BM AI", sortKey: "aiProjection", align: "right" },
  { key: "aiDelta", label: "AI Δ", sortKey: "aiDelta", align: "right" },
  { key: "aiConfidence", label: "AI Conf", sortKey: "aiConfidence", align: "right" },
  { key: "aiGrade", label: "AI Grade", sortKey: "aiGrade", align: "right" },
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
  showProjectionComparison = false,
  hasAiProjections = false,
}: {
  players: PoolPlayerRow[];
  locks: Set<string>;
  exclusions: Set<string>;
  maxExposure: Record<string, number>;
  onToggleLock: (dkPlayerId: string) => void;
  onToggleExclude: (dkPlayerId: string) => void;
  onExposureChange: (dkPlayerId: string, fraction: number) => void;
  showProjectionComparison?: boolean;
  hasAiProjections?: boolean;
}) {
  const [positionTab, setPositionTab] = useState<PoolTableTab>("ALL");
  const [teamFilter, setTeamFilter] = useState(ALL_TEAMS);
  const [gameFilter, setGameFilter] = useState(ALL_GAMES);
  const [starterFilter, setStarterFilter] = useState<StarterFilter>("ALL");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof PoolPlayerRow>("projection");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");
  const [detailPlayer, setDetailPlayer] = useState<PoolPlayerRow | null>(null);

  const columns = useMemo(() => {
    let cols = COLUMNS;
    if (hasAiProjections) {
      const nativeDeltaIndex = cols.findIndex((c) => c.key === "nativeDelta");
      cols = [...cols.slice(0, nativeDeltaIndex + 1), ...AI_COLUMNS, ...cols.slice(nativeDeltaIndex + 1)];
    }
    if (showProjectionComparison) {
      const projIndex = cols.findIndex((c) => c.key === "projection");
      cols = [...cols.slice(0, projIndex + 1), ...COMPARISON_COLUMNS, ...cols.slice(projIndex + 1)];
    }
    return cols;
  }, [showProjectionComparison, hasAiProjections]);

  const teamOptions = useMemo(() => distinctValues(players, (p) => p.team), [players]);
  // "TEAM @ OPP" labeled by (alphabetically-lower team) @ (alphabetically-higher team),
  // so both sides of the same game always produce the identical label/gameId pair.
  const gameOptions = useMemo(() => {
    const byGameId = new Map<string, string>();
    for (const p of players) {
      if (!p.gameId || byGameId.has(p.gameId)) continue;
      const teams = [p.team, p.opponent ?? "?"].sort();
      byGameId.set(p.gameId, `${teams[0]} @ ${teams[1]}`);
    }
    return Array.from(byGameId.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [players]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return players.filter((p) => {
      if (positionTab === "P" && p.playerType !== "pitcher") return false;
      if (positionTab === "HIT" && p.playerType !== "hitter") return false;
      if (positionTab !== "ALL" && positionTab !== "P" && positionTab !== "HIT" && !p.positions.includes(positionTab)) return false;
      if (teamFilter !== ALL_TEAMS && p.team !== teamFilter) return false;
      if (gameFilter !== ALL_GAMES && p.gameId !== gameFilter) return false;
      if (starterFilter === "CONFIRMED" && p.lineupConfirmation !== "CONFIRMED") return false;
      if (starterFilter === "PROBABLE" && p.lineupConfirmation !== "PROBABLE") return false;
      if (q && !p.name.toLowerCase().includes(q) && !p.team.toLowerCase().includes(q) && !(p.opponent ?? "").toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [players, positionTab, teamFilter, gameFilter, starterFilter, search]);

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
          {POOL_TABLE_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setPositionTab(tab)}
              className={`rounded px-2 py-1 text-xs font-medium uppercase tracking-wide ${
                positionTab === tab ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-faint hover:text-text-muted"
              }`}
            >
              {tab === "HIT" ? "Hitters" : tab === "P" ? "Pitchers" : tab}
            </button>
          ))}
        </div>
        <select
          value={starterFilter}
          onChange={(e) => setStarterFilter(e.target.value as StarterFilter)}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none focus:border-accent"
        >
          <option value="ALL">All Starters</option>
          <option value="CONFIRMED">Confirmed Starters</option>
          <option value="PROBABLE">Probable Starters</option>
        </select>
        <select
          value={teamFilter}
          onChange={(e) => setTeamFilter(e.target.value)}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none focus:border-accent"
        >
          <option value={ALL_TEAMS}>All Teams</option>
          {teamOptions.map((team) => (
            <option key={team} value={team}>
              {team}
            </option>
          ))}
        </select>
        <select
          value={gameFilter}
          onChange={(e) => setGameFilter(e.target.value)}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none focus:border-accent"
        >
          <option value={ALL_GAMES}>All Games</option>
          {gameOptions.map(([gameId, label]) => (
            <option key={gameId} value={gameId}>
              {label}
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

      <div className="max-h-[560px] overflow-auto rounded-[var(--radius-control)] border border-border">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg-panel-raised">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={col.sortKey ? () => handleSort(col.sortKey!) : undefined}
                  className={`border-b border-border p-0 text-[11px] uppercase tracking-wide text-text-faint ${
                    col.align === "right" ? "text-right" : "text-left"
                  } ${col.sortKey ? "cursor-pointer select-none hover:text-text-muted" : ""}`}
                >
                  {/* Resizable column header (CSS `resize`, no library): drag
                      the bottom-right handle to widen/narrow a column. */}
                  <div className="min-w-[3rem] resize-x overflow-hidden whitespace-nowrap px-2 py-1.5">
                    {col.label}
                    {col.sortKey === sortKey ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                  </div>
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
                  <td className="px-2 py-1 font-medium text-text">
                    <button type="button" onClick={() => setDetailPlayer(p)} className="text-left hover:underline">
                      {p.name}
                    </button>
                  </td>
                  <td className="px-2 py-1 text-text-muted">{p.team}</td>
                  <td className="px-2 py-1 text-text-muted">{p.opponent ?? "--"}</td>
                  <td className="px-2 py-1">
                    {(() => {
                      const elig = formatEligibilityStatus(p.eligibilityStatus, p.lineupConfirmation);
                      const toneClass =
                        elig.tone === "starting" ? "bg-green/15 text-green"
                        : elig.tone === "probable" ? "bg-purple/15 text-purple"
                        : elig.tone === "bench" ? "bg-bg-panel-raised text-text-muted"
                        : elig.tone === "unconfirmed" ? "bg-yellow/15 text-yellow"
                        : "bg-red/10 text-red";
                      const isProbable = p.eligibilityStatus === "PROBABLE_HITTER" || (p.eligibilityStatus === "STARTING_PITCHER" && p.lineupConfirmation === "PROBABLE");
                      return (
                        <span className="inline-flex flex-col gap-0.5" title={p.probableReason ?? undefined}>
                          <span className={`whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium ${toneClass}`}>{elig.label}</span>
                          {isProbable && p.probableConfidence && (
                            <span className="whitespace-nowrap text-[9px] font-medium uppercase tracking-wide text-purple/70">
                              Confidence: {p.probableConfidence}
                            </span>
                          )}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-2 py-1 text-right text-text-muted">
                    {p.playerType === "pitcher" ? "" : (
                      p.battingOrder ?? (p.projectedBattingOrder != null ? <span className="italic text-purple/70">Proj: {p.projectedBattingOrder}</span> : "--")
                    )}
                  </td>
                  <td className="px-2 py-1 text-right text-text">${p.salary.toLocaleString()}</td>
                  <td className="px-2 py-1 text-right text-text">{fmt(p.projection)}</td>
                  {showProjectionComparison && (
                    <>
                      <td className="px-2 py-1 text-right text-text-muted">{fmt(p.externalProjection)}</td>
                      <td className="px-2 py-1 text-right text-text-muted">{fmt(p.adjustedProjection)}</td>
                      <td className={`px-2 py-1 text-right ${p.adjustmentDelta !== null && p.adjustmentDelta >= 0 ? "text-green" : p.adjustmentDelta !== null ? "text-red" : "text-text-muted"}`}>
                        {p.adjustmentDelta !== null ? `${p.adjustmentDelta >= 0 ? "+" : ""}${fmt(p.adjustmentDelta)}` : "--"}
                      </td>
                    </>
                  )}
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.ceiling)}</td>
                  <td className="px-2 py-1 text-right text-text-muted">{fmt(p.value, 2)}</td>
                  <td className="px-2 py-1 text-right text-purple">{fmt(p.nativeProjection)}</td>
                  <td className={`px-2 py-1 text-right ${p.nativeDelta !== null && p.nativeDelta >= 0 ? "text-green" : p.nativeDelta !== null ? "text-red" : "text-text-muted"}`}>
                    {p.nativeDelta !== null ? `${p.nativeDelta >= 0 ? "+" : ""}${fmt(p.nativeDelta, 2)}` : "--"}
                  </td>
                  {hasAiProjections && (
                    <>
                      <td className="px-2 py-1 text-right text-purple">{fmt(p.aiProjection)}</td>
                      <td className={`px-2 py-1 text-right ${p.aiDelta !== null && p.aiDelta >= 0 ? "text-green" : p.aiDelta !== null ? "text-red" : "text-text-muted"}`}>
                        {p.aiDelta !== null ? `${p.aiDelta >= 0 ? "+" : ""}${fmt(p.aiDelta, 2)}` : "--"}
                      </td>
                      <td className="px-2 py-1 text-right text-text-muted">{fmt(p.aiConfidence, 0)}</td>
                      <td className="px-2 py-1 text-right text-purple">{p.aiGrade ?? "--"}</td>
                    </>
                  )}
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
                <td colSpan={columns.length} className="px-2 py-6 text-center text-text-faint">
                  No players match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {detailPlayer && <PlayerDetailModal player={detailPlayer} onClose={() => setDetailPlayer(null)} />}
    </div>
  );
}
