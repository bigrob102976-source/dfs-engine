"use client";

import { useMemo, useState } from "react";

import { DkSlateCoverageSummary } from "./DkSlateCoverageSummary";
import { VegasFilterBar } from "./VegasFilterBar";
import { VegasMobileCard } from "./VegasMobileCard";
import { VegasSettingsToggles } from "./VegasSettingsToggles";
import { VegasSummaryCards } from "./VegasSummaryCards";
import { VegasTable } from "./VegasTable";
import type { DkSlateVegasCoverage } from "@/lib/dkVegasCoverage";
import type { SlateEnvironmentReport } from "@/lib/gameEnvironment";
import { useVegasDisplaySettings } from "@/lib/vegasDisplaySettings";
import { buildVegasSummaryStats, type VegasGameRow } from "@/lib/vegasIntelligence";
import { filterVegasRows, searchVegasRows, sortVegasRows, type VegasFilterKey, type VegasSortKey } from "@/lib/vegasSortFilter";

type MarketView = "pregame" | "live";

/** Milestone 25: swaps each row's `game.vegas` for `game.vegas_live`
 * when the user selects the LIVE MARKET tab -- every existing table/
 * card/expanded-detail component only ever reads `game.vegas`, so this
 * is the one place the tab's meaning is applied, reusing all of that
 * rendering rather than duplicating it. Falls back to the pregame value
 * when a game has no live snapshot (e.g. mock mode, which never
 * populates vegas_live) so the LIVE MARKET tab never goes blank. */
function withMarketView(rows: VegasGameRow[], view: MarketView): VegasGameRow[] {
  if (view === "pregame") return rows;
  return rows.map((row) => ({ ...row, game: { ...row.game, vegas: row.game.vegas_live ?? row.game.vegas } }));
}

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
  coverage,
}: {
  report: SlateEnvironmentReport;
  rows: VegasGameRow[];
  history: SlateEnvironmentReport[];
  coverage: DkSlateVegasCoverage;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<VegasFilterKey>("all");
  const [sortKey, setSortKey] = useState<VegasSortKey>("gameTime");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [settings, setSetting] = useVegasDisplaySettings();
  const [marketView, setMarketView] = useState<MarketView>("pregame");

  const stats = useMemo(() => buildVegasSummaryStats(report), [report]);

  const marketRows = useMemo(() => withMarketView(rows, marketView), [rows, marketView]);

  const visible = useMemo(() => {
    const filtered = filterVegasRows(marketRows, filter);
    const searched = searchVegasRows(filtered, search);
    return sortVegasRows(searched, sortKey, sortDir);
  }, [marketRows, filter, search, sortKey, sortDir]);

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
      <DkSlateCoverageSummary coverage={coverage} />

      <VegasSummaryCards stats={stats} />

      {/* Milestone 25: PREGAME DFS (default) is what Big Money DFS
          projections actually use; LIVE MARKET is research/history only
          -- swaps every row's displayed vegas for vegas_live, never the
          other way around. */}
      <div
        role="tablist"
        aria-label="Vegas market view"
        className="flex w-fit rounded-[var(--radius-control)] border border-border bg-bg-panel-raised p-1 text-xs"
      >
        <button
          type="button"
          role="tab"
          aria-selected={marketView === "pregame"}
          onClick={() => setMarketView("pregame")}
          className={`rounded-[var(--radius-control)] px-3 py-1.5 font-semibold uppercase tracking-wide transition-colors duration-150 ${
            marketView === "pregame" ? "bg-accent text-white" : "text-text-faint hover:text-text"
          }`}
        >
          Pregame DFS
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={marketView === "live"}
          onClick={() => setMarketView("live")}
          className={`rounded-[var(--radius-control)] px-3 py-1.5 font-semibold uppercase tracking-wide transition-colors duration-150 ${
            marketView === "live" ? "bg-accent text-white" : "text-text-faint hover:text-text"
          }`}
        >
          Live Market
        </button>
      </div>
      {marketView === "live" && (
        <p className="-mt-2 text-[11px] text-yellow">
          Showing CURRENT market data, including in-play/final games. Big Money DFS projections never use this view -- see Pregame DFS.
        </p>
      )}

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
        marketView={marketView}
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
            marketView={marketView}
          />
        ))}
        {visible.length === 0 && <p className="py-8 text-center text-xs text-text-faint">No games match the current filters.</p>}
      </div>
    </div>
  );
}
