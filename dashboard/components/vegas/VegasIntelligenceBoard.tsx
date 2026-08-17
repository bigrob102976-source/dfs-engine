"use client";

import { useMemo, useState } from "react";

import { VegasFilterBar } from "./VegasFilterBar";
import { VegasMobileCard } from "./VegasMobileCard";
import { VegasSettingsToggles } from "./VegasSettingsToggles";
import { VegasSummaryCards } from "./VegasSummaryCards";
import { VegasTable } from "./VegasTable";
import type { SlateEnvironmentReport } from "@/lib/gameEnvironment";
import { useVegasDisplaySettings } from "@/lib/vegasDisplaySettings";
import { buildVegasSummaryStats, type VegasGameRow } from "@/lib/vegasIntelligence";
import { filterVegasRows, searchVegasRows, sortVegasRows, type VegasFilterKey, type VegasSortKey } from "@/lib/vegasSortFilter";

/** Client-side interactive shell for the Vegas Intelligence Board
 * (Milestone DS3): summary cards, search/filter/sort toolbar, the
 * desktop table / mobile card split, row expansion, and the
 * Show-First-Observed-Lines/Movement-%/Sparklines/Compact-Mode display
 * settings. The Server Component page (page.tsx) does the one-time file
 * read (+ pitcher join); everything interactive lives here -- same
 * split as EnvironmentTerminal. */
export function VegasIntelligenceBoard({
  report,
  rows,
  history,
}: {
  report: SlateEnvironmentReport;
  rows: VegasGameRow[];
  history: SlateEnvironmentReport[];
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<VegasFilterKey>("all");
  const [sortKey, setSortKey] = useState<VegasSortKey>("gameTime");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [settings, setSetting] = useVegasDisplaySettings();

  const stats = useMemo(() => buildVegasSummaryStats(report), [report]);

  const visible = useMemo(() => {
    const filtered = filterVegasRows(rows, filter);
    const searched = searchVegasRows(filtered, search);
    return sortVegasRows(searched, sortKey, sortDir);
  }, [rows, filter, search, sortKey, sortDir]);

  function handleSort(key: VegasSortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function toggleExpand(gameId: string) {
    setExpandedId((current) => (current === gameId ? null : gameId));
  }

  return (
    <div className="flex flex-col gap-4">
      <VegasSummaryCards stats={stats} />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
        <VegasSettingsToggles settings={settings} onChange={setSetting} />
      </div>

      <VegasFilterBar
        resultCount={`${visible.length} / ${rows.length} games`}
        search={search}
        onSearchChange={setSearch}
        filter={filter}
        onFilterChange={setFilter}
        sortKey={sortKey}
        onSortChange={(key) => {
          setSortKey(key);
          setSortDir(key === "gameTime" ? "asc" : "desc");
        }}
      />

      <VegasTable
        rows={visible}
        analysis={report.vegas_slate_analysis}
        settings={settings}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
        expandedId={expandedId}
        onToggleExpand={toggleExpand}
        history={history}
      />

      <div className="flex flex-col gap-3 lg:hidden">
        {visible.map((row) => (
          <VegasMobileCard
            key={row.game.game_id}
            row={row}
            analysis={report.vegas_slate_analysis}
            settings={settings}
            expanded={expandedId === row.game.game_id}
            onToggleExpand={() => toggleExpand(row.game.game_id)}
            history={history}
          />
        ))}
        {visible.length === 0 && <p className="py-8 text-center text-xs text-text-faint">No games match the current filters.</p>}
      </div>
    </div>
  );
}
