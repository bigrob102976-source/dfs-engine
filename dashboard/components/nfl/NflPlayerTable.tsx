"use client";

import { useMemo, useState } from "react";

import { DangerButton, PrimaryButton, SearchInput, TableToolbar } from "@/components/ui";
import { fmt, fmtOwnership, fmtSalary, fmtValue, identityLabel, projectionLabel } from "@/lib/nfl/format";
import { loadLockExcludeState, saveLockExcludeState } from "@/lib/nfl/lockExcludeStorage";
import { NFL_POSITIONS, type NflPlayerRow } from "@/lib/nfl/types";

type Variant = "players" | "usage" | "projections" | "matchups";

const POSITION_TABS = ["ALL", ...NFL_POSITIONS] as const;

function positionOf(p: NflPlayerRow): string {
  return p.is_team_entity ? "DST" : p.position;
}

// NFL UI M1 -- position-aware "recent usage" summary shown in the
// Players tab (Phase spec: QB=attempts/rush, RB=carries/targets,
// WR/TE=targets/receptions, DST=sacks/INT/points allowed). Reads ONLY
// real rolling_features keys that exist -- never invents a field.
function recentUsageSummary(p: NflPlayerRow): string {
  const r = p.usage?.rolling;
  if (!r) return "--";
  if (p.is_team_entity) {
    const sacks = r["sacks_mean_last3"];
    const ints = r["interceptions_mean_last3"];
    const pa = r["points_allowed_mean_last3"];
    return `${fmt(sacks)} sk / ${fmt(ints)} int / ${fmt(pa)} PA`;
  }
  if (p.position === "QB") return `${fmt(r["pass_attempts_mean_last3"], 0)} att / ${fmt(r["carries_mean_last3"], 0)} rush`;
  if (p.position === "RB") return `${fmt(r["carries_mean_last3"], 0)} car / ${fmt(r["targets_mean_last3"], 0)} tgt`;
  return `${fmt(r["targets_mean_last3"], 0)} tgt / ${fmt(r["receptions_mean_last3"], 0)} rec`;
}

function snapPct(p: NflPlayerRow): number | null {
  return p.usage?.rolling["snap_share_mean_last3"] ?? null;
}

export function NflPlayerTable({ players, draftGroupId, variant = "players" }: { players: NflPlayerRow[]; draftGroupId: number; variant?: Variant }) {
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState<string>("ALL");
  const [team, setTeam] = useState<string>("ALL");
  const [sortKey, setSortKey] = useState<string>("salary");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [lockExclude, setLockExclude] = useState(() => loadLockExcludeState(draftGroupId));

  const teams = useMemo(() => Array.from(new Set(players.map((p) => p.team))).sort(), [players]);

  function toggleLock(id: string) {
    setLockExclude((prev) => {
      const locks = prev.locks.includes(id) ? prev.locks.filter((x) => x !== id) : [...prev.locks, id];
      const excludes = prev.excludes.filter((x) => x !== id);
      const next = { locks, excludes };
      saveLockExcludeState(draftGroupId, next);
      return next;
    });
  }
  function toggleExclude(id: string) {
    setLockExclude((prev) => {
      const excludes = prev.excludes.includes(id) ? prev.excludes.filter((x) => x !== id) : [...prev.excludes, id];
      const locks = prev.locks.filter((x) => x !== id);
      const next = { locks, excludes };
      saveLockExcludeState(draftGroupId, next);
      return next;
    });
  }

  const filtered = useMemo(() => {
    let rows = players;
    if (position !== "ALL") rows = rows.filter((p) => positionOf(p) === position);
    if (team !== "ALL") rows = rows.filter((p) => p.team === team);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((p) => p.name.toLowerCase().includes(q));
    }
    const sorted = [...rows].sort((a, b) => {
      const valueOf = (p: NflPlayerRow): number | null => {
        switch (sortKey) {
          case "salary":
            return p.salary;
          case "projection":
            return p.projection?.projection ?? null;
          case "ceiling":
            return p.projection?.ceiling ?? null;
          case "snap":
            return snapPct(p);
          case "ownership":
            return p.ownership?.ownership_projection ?? null;
          default:
            return p.salary;
        }
      };
      const av = valueOf(a);
      const bv = valueOf(b);
      if (av === null && bv === null) return 0;
      if (av === null) return 1; // nulls always sort last
      if (bv === null) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return sorted;
  }, [players, position, team, search, sortKey, sortDir]);

  function sortButton(key: string, label: string) {
    return (
      <button
        onClick={() => {
          if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
          else {
            setSortKey(key);
            setSortDir("desc");
          }
        }}
        className={`font-medium ${sortKey === key ? "text-accent" : "text-text-faint"}`}
      >
        {label} {sortKey === key ? (sortDir === "asc" ? "↑" : "↓") : ""}
      </button>
    );
  }

  return (
    <div className="space-y-3">
      <TableToolbar resultCount={`${filtered.length}`}>
        <SearchInput value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search players…" />
        <div className="flex gap-1">
          {POSITION_TABS.map((pos) => (
            <button
              key={pos}
              onClick={() => setPosition(pos)}
              className={`rounded-[var(--radius-control)] px-2 py-1 text-xs font-semibold ${
                position === pos ? "bg-accent/15 text-accent" : "text-text-faint hover:text-text-muted"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>
        <select value={team} onChange={(e) => setTeam(e.target.value)} className="rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text">
          <option value="ALL">All Teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </TableToolbar>

      <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="sticky top-0 border-b border-border-subtle bg-bg-panel-raised text-text-faint">
              {variant === "players" && <th className="px-2 py-2">Lock</th>}
              {variant === "players" && <th className="px-2 py-2">Excl</th>}
              <th className="px-2 py-2">Pos</th>
              <th className="px-2 py-2">Player</th>
              <th className="px-2 py-2">Team</th>
              <th className="px-2 py-2">Opp</th>
              {variant !== "usage" && <th className="px-2 py-2">{sortButton("salary", "Salary")}</th>}
              {variant !== "usage" && <th className="px-2 py-2">{sortButton("projection", "Projection")}</th>}
              {variant !== "usage" && <th className="px-2 py-2">Floor</th>}
              {variant !== "usage" && <th className="px-2 py-2">{sortButton("ceiling", "Ceiling")}</th>}
              {variant !== "usage" && <th className="px-2 py-2">Value</th>}
              {variant === "projections" && <th className="px-2 py-2">Model</th>}
              {(variant === "players" || variant === "projections") && <th className="px-2 py-2">{sortButton("ownership", "Ownership")}</th>}
              {variant === "players" && <th className="px-2 py-2">{sortButton("snap", "Snap %")}</th>}
              {variant === "players" && <th className="px-2 py-2">Recent Usage</th>}
              {variant === "matchups" && <th className="px-2 py-2">Home/Away</th>}
              {variant === "matchups" && <th className="px-2 py-2">Total</th>}
              {variant === "matchups" && <th className="px-2 py-2">Spread</th>}
              <th className="px-2 py-2">Identity</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const isLocked = lockExclude.locks.includes(p.draftkings_player_id);
              const isExcluded = lockExclude.excludes.includes(p.draftkings_player_id);
              return (
                <tr key={p.draftkings_player_id} className="border-b border-border-subtle/50 hover:bg-bg-panel-raised/50">
                  {variant === "players" && (
                    <td className="px-2 py-1.5">
                      <PrimaryButton onClick={() => toggleLock(p.draftkings_player_id)} className={`px-2 py-0.5 text-[10px] ${isLocked ? "" : "opacity-40"}`}>
                        {isLocked ? "Locked" : "Lock"}
                      </PrimaryButton>
                    </td>
                  )}
                  {variant === "players" && (
                    <td className="px-2 py-1.5">
                      <DangerButton onClick={() => toggleExclude(p.draftkings_player_id)} className={`px-2 py-0.5 text-[10px] ${isExcluded ? "" : "opacity-40"}`}>
                        {isExcluded ? "Excluded" : "Exclude"}
                      </DangerButton>
                    </td>
                  )}
                  <td className="px-2 py-1.5 text-text-muted">{positionOf(p)}</td>
                  <td className="px-2 py-1.5 font-medium text-text">{p.name}</td>
                  <td className="px-2 py-1.5 text-text-muted">{p.team}</td>
                  <td className="px-2 py-1.5 text-text-muted">{p.opponent ?? "--"}</td>
                  {variant !== "usage" && <td className="px-2 py-1.5 text-text-muted">{fmtSalary(p.salary)}</td>}
                  {variant !== "usage" && <td className="px-2 py-1.5 font-semibold text-text">{fmt(p.projection?.projection)}</td>}
                  {variant !== "usage" && <td className="px-2 py-1.5 text-text-muted">{fmt(p.projection?.floor)}</td>}
                  {variant !== "usage" && <td className="px-2 py-1.5 text-text-muted">{fmt(p.projection?.ceiling)}</td>}
                  {variant !== "usage" && <td className="px-2 py-1.5 text-text-muted">{fmtValue(p.projection?.projection, p.salary)}</td>}
                  {variant === "projections" && <td className="px-2 py-1.5 text-[10px] text-text-faint">{projectionLabel(p.projection?.source)}</td>}
                  {(variant === "players" || variant === "projections") && (
                    <td className="px-2 py-1.5 text-text-muted" title={p.ownership?.ownership_tier ? `Tier: ${p.ownership.ownership_tier}` : undefined}>
                      {fmtOwnership(p.ownership?.ownership_projection)}
                    </td>
                  )}
                  {variant === "players" && <td className="px-2 py-1.5 text-text-muted">{fmt(snapPct(p) !== null ? (snapPct(p) as number) * 100 : null, 0)}{snapPct(p) !== null ? "%" : ""}</td>}
                  {variant === "players" && <td className="px-2 py-1.5 text-text-muted">{recentUsageSummary(p)}</td>}
                  {variant === "matchups" && <td className="px-2 py-1.5 text-text-muted">--</td>}
                  {variant === "matchups" && <td className="px-2 py-1.5 text-text-muted">{fmt(p.matchup?.total)}</td>}
                  {variant === "matchups" && <td className="px-2 py-1.5 text-text-muted">{fmt(p.matchup?.spread_home)}</td>}
                  <td className="px-2 py-1.5 text-[10px] text-text-faint">{identityLabel(p)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
