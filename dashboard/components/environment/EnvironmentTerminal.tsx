"use client";

import { useMemo, useState } from "react";

import { GameEnvironmentCard } from "@/components/environment/GameEnvironmentCard";
import { GameEnvironmentDrawer } from "@/components/environment/GameEnvironmentDrawer";
import { TableToolbar } from "@/components/ui/TableToolbar";
import { useEnvironmentSections } from "@/lib/environmentDisplaySettings";
import { filterGamesByPark, sortGames, type EnvironmentSortKey, type ParkFilter } from "@/lib/environmentSortFilter";
import type { GameEnvironmentReport } from "@/lib/gameEnvironment";

const SORT_OPTIONS: Array<{ value: EnvironmentSortKey; label: string }> = [
  { value: "score", label: "Environment Score" },
  { value: "total", label: "Highest Totals" },
  { value: "weatherRisk", label: "Weather Risk" },
  { value: "bullpenRisk", label: "Bullpen Risk" },
  { value: "stack", label: "Highest Stack Rating" },
];

/** Client-side grid + filter/sort controls + detail drawer for a slate's
 * Game Environment reports. The Server Component page (page.tsx) does the
 * one-time file read; everything interactive lives here. */
export function EnvironmentTerminal({ games }: { games: GameEnvironmentReport[] }) {
  const [sortKey, setSortKey] = useState<EnvironmentSortKey>("score");
  const [parkFilter, setParkFilter] = useState<ParkFilter>("all");
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [sections] = useEnvironmentSections();

  const visible = useMemo(() => sortGames(filterGamesByPark(games, parkFilter), sortKey), [games, parkFilter, sortKey]);
  const selectedGame = visible.find((g) => g.game_id === selectedGameId) ?? games.find((g) => g.game_id === selectedGameId) ?? null;

  return (
    <div>
      <TableToolbar resultCount={`${visible.length} / ${games.length} games`}>
        <label className="flex items-center gap-1.5 text-xs text-text-faint">
          Sort by
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as EnvironmentSortKey)}
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-text-faint">
          Park
          <select
            value={parkFilter}
            onChange={(e) => setParkFilter(e.target.value as ParkFilter)}
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
          >
            <option value="all">All Parks</option>
            <option value="hitter">Hitter Parks</option>
            <option value="pitcher">Pitcher&apos;s Parks</option>
          </select>
        </label>
      </TableToolbar>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {visible.map((game) => (
          <GameEnvironmentCard key={game.game_id} game={game} sections={sections} onOpen={() => setSelectedGameId(game.game_id)} />
        ))}
        {visible.length === 0 && (
          <p className="col-span-full py-8 text-center text-xs text-text-faint">No games match the current filters.</p>
        )}
      </div>

      <GameEnvironmentDrawer game={selectedGame} sections={sections} onClose={() => setSelectedGameId(null)} />
    </div>
  );
}
