"use client";

import { useMemo, useState } from "react";

import { PlayerDetailPanel } from "@/components/PlayerDetailPanel";
import { HITTER_COLUMNS, PITCHER_COLUMNS, type PlayerColumn } from "@/components/playerColumns";
import { distinctValues, filterPlayerRows, sortRows, type PlayerRowFilters } from "@/lib/sortFilter";
import type { PlayerRow } from "@/lib/types";

export type { PlayerColumn } from "@/components/playerColumns";

/** `variant` is a plain, serializable string a Server Component page can
 * pass safely -- PlayerTable resolves it to a pre-built, client-only
 * column set itself. `columns` (a literal array with JSX render
 * closures) is still accepted directly for client-side callers, e.g.
 * component tests, but a Server Component page must use `variant`
 * instead: functions cannot be passed as props across the RSC boundary. */
export function PlayerTable({
  rows,
  columns,
  variant,
  initialSortKey,
  highlightId,
  showFilters = true,
  initialFilters,
}: {
  rows: PlayerRow[];
  columns?: PlayerColumn[];
  variant?: "pitcher" | "hitter";
  initialSortKey: keyof PlayerRow;
  highlightId?: string | null;
  showFilters?: boolean;
  /** Seeds the filter state on mount -- e.g. a `?team=` query param from
   * the Vegas Intelligence Board's "Top Hitters"/"Top Pitchers" links.
   * A plain serializable object, so a Server Component page can pass it
   * directly (unlike `columns`, which carries render closures). */
  initialFilters?: PlayerRowFilters;
}) {
  const resolvedColumns = columns ?? (variant === "pitcher" ? PITCHER_COLUMNS : HITTER_COLUMNS);
  const [sortKey, setSortKey] = useState<keyof PlayerRow>(initialSortKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [filters, setFilters] = useState<PlayerRowFilters>(() => initialFilters ?? {});
  // Lazy initializer (not an effect): a highlighted player from a search
  // result should open the detail panel on first render only -- each
  // navigation to this route mounts a fresh PlayerTable instance, so
  // there's no "prop changed after mount" case to synchronize against.
  const [selected, setSelected] = useState<PlayerRow | null>(() =>
    highlightId ? (rows.find((r) => r.id === highlightId) ?? null) : null,
  );

  const teams = useMemo(() => distinctValues(rows, (r) => r.team), [rows]);
  const positions = useMemo(() => distinctValues(rows, (r) => r.position), [rows]);
  const tiers = useMemo(() => distinctValues(rows, (r) => r.ownershipTier), [rows]);
  const tags = useMemo(() => distinctValues(rows, (r) => r.tags.join(",")).flatMap((t) => t.split(",")), [rows]);
  const uniqueTags = useMemo(() => Array.from(new Set(tags)).sort(), [tags]);

  const filtered = useMemo(() => filterPlayerRows(rows, filters), [rows, filters]);
  const sorted = useMemo(() => sortRows(filtered, sortKey, sortDir), [filtered, sortKey, sortDir]);

  function toggleSort(key: keyof PlayerRow) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div>
      {showFilters && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            placeholder="Filter by name..."
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text outline-none focus:border-accent"
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value || undefined }))}
          />
          <select
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
            onChange={(e) => setFilters((f) => ({ ...f, team: e.target.value || undefined }))}
            defaultValue={filters.team ?? ""}
          >
            <option value="">All teams</option>
            {teams.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
            onChange={(e) => setFilters((f) => ({ ...f, position: e.target.value || undefined }))}
            defaultValue=""
          >
            <option value="">All positions</option>
            {positions.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
            onChange={(e) => setFilters((f) => ({ ...f, ownershipTier: e.target.value || undefined }))}
            defaultValue=""
          >
            <option value="">All ownership tiers</option>
            {tiers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {uniqueTags.length > 0 && (
            <select
              className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
              onChange={(e) => setFilters((f) => ({ ...f, tag: e.target.value || undefined }))}
              defaultValue=""
            >
              <option value="">All tags</option>
              {uniqueTags.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          )}
          <span className="text-xs text-text-faint">
            {sorted.length} / {rows.length}
          </span>
        </div>
      )}

      <div className="max-h-[640px] overflow-auto rounded-[var(--radius-control)] border border-border shadow-[var(--shadow-card)]">
        <table className="text-xs">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-border bg-bg-panel-raised">
              <th className="px-2 py-1.5 text-text-faint">#</th>
              {resolvedColumns.map((col) => (
                <th
                  key={col.key}
                  onClick={col.sortKey ? () => toggleSort(col.sortKey!) : undefined}
                  className={`px-2 py-1.5 text-text-faint ${col.align === "right" ? "text-right" : "text-left"} ${
                    col.sortKey ? "cursor-pointer select-none hover:text-text" : ""
                  }`}
                >
                  {col.label}
                  {col.sortKey === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.id}
                onClick={() => setSelected(row)}
                className="cursor-pointer border-b border-border-subtle hover:bg-bg-panel-raised"
              >
                <td className="px-2 py-1.5 text-text-faint">{i + 1}</td>
                {resolvedColumns.map((col) => (
                  <td key={col.key} className={`px-2 py-1.5 text-text ${col.align === "right" ? "text-right" : ""}`}>
                    {col.render ? col.render(row) : "--"}
                  </td>
                ))}
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={resolvedColumns.length + 1} className="px-2 py-6 text-center text-text-faint">
                  No players match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <PlayerDetailPanel row={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
