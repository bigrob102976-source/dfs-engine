"use client";

import { SearchInput } from "@/components/ui/SearchInput";
import { TableToolbar } from "@/components/ui/TableToolbar";
import type { VegasFilterKey, VegasSortKey } from "@/lib/vegasSortFilter";

const FILTER_OPTIONS: Array<{ value: VegasFilterKey; label: string }> = [
  { value: "all", label: "All Games" },
  { value: "gameTotal", label: "Game Total" },
  { value: "highestTotals", label: "Highest Totals" },
  { value: "lowestTotals", label: "Lowest Totals" },
  { value: "largestMoves", label: "Largest Line Moves" },
  { value: "sharpMoney", label: "Sharp Money" },
  { value: "weatherRisk", label: "Weather Risk" },
  { value: "highestImplied", label: "Highest Implied Runs" },
  { value: "lowestImplied", label: "Lowest Implied Runs" },
];

const SORT_OPTIONS: Array<{ value: VegasSortKey; label: string }> = [
  { value: "gameTime", label: "Game Time" },
  { value: "totalCurrent", label: "Game Total" },
  { value: "totalMovement", label: "Total Movement" },
  { value: "moneylineMovement", label: "Moneyline Movement" },
  { value: "homeImplied", label: "Home Implied Runs" },
  { value: "awayImplied", label: "Away Implied Runs" },
  { value: "environmentScore", label: "Environment Score" },
  { value: "vegasScore", label: "Vegas Score" },
];

export function VegasFilterBar({
  resultCount,
  search,
  onSearchChange,
  filter,
  onFilterChange,
  sortKey,
  onSortChange,
}: {
  resultCount: string;
  search: string;
  onSearchChange: (value: string) => void;
  filter: VegasFilterKey;
  onFilterChange: (value: VegasFilterKey) => void;
  sortKey: VegasSortKey;
  onSortChange: (value: VegasSortKey) => void;
}) {
  return (
    <TableToolbar resultCount={resultCount}>
      <SearchInput
        placeholder="Search team, opponent, or pitcher..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        aria-label="Search Vegas board"
      />
      <label className="flex items-center gap-1.5 text-xs text-text-faint">
        Filter
        <select
          value={filter}
          onChange={(e) => onFilterChange(e.target.value as VegasFilterKey)}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
        >
          {FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5 text-xs text-text-faint">
        Sort by
        <select
          value={sortKey}
          onChange={(e) => onSortChange(e.target.value as VegasSortKey)}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    </TableToolbar>
  );
}
