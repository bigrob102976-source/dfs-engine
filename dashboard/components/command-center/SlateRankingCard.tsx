import { SlateRankingBadgeRow } from "./SlateRankingBadgeRow";
import type { GameRanking } from "@/lib/commandCenter";

function fmt(v: number | null, digits = 0): string {
  return v === null ? "--" : v.toFixed(digits);
}
function formatGameTime(iso: string | null): string {
  if (!iso) return "Time TBD";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "Time TBD" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** CENTER COLUMN: one card per game, ranked by combined score
 * (highest priority first). Clicking opens the Game Center slide-over.
 * Every score shown is either read straight from the Game Environment
 * snapshot or a trivial average of already-computed scores -- see
 * lib/commandCenter.ts::buildGameRankings. */
export function SlateRankingCard({ rank, ranking, onOpen }: { rank: number; ranking: GameRanking; onOpen: () => void }) {
  const { game } = ranking;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-2.5 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 text-left shadow-[var(--shadow-card)] transition-all duration-150 hover:-translate-y-0.5 hover:border-accent hover:shadow-[var(--shadow-popover)]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-dim text-[10px] font-bold text-accent">{rank}</span>
          <div>
            <div className="text-sm font-semibold text-text">
              {game.away_team} @ {game.home_team}
            </div>
            <div className="text-[11px] text-text-faint">
              {formatGameTime(game.game_datetime_utc)}
              {game.venue_name ? ` · ${game.venue_name}` : ""}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wide text-text-faint">Combined</div>
          <div className="text-lg font-semibold tabular-nums text-gold">{ranking.combinedScore.toFixed(0)}</div>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-1.5 text-center text-[10px]">
        <div>
          <div className="text-text-faint">Vegas</div>
          <div className="font-semibold text-text">{fmt(ranking.vegasScoreValue)}</div>
        </div>
        <div>
          <div className="text-text-faint">Env</div>
          <div className="font-semibold text-text">{fmt(ranking.environmentScore)}</div>
        </div>
        <div>
          <div className="text-text-faint">Weather</div>
          <div className="font-semibold text-text">{fmt(ranking.weatherScore)}</div>
        </div>
        <div>
          <div className="text-text-faint">Stack</div>
          <div className="font-semibold text-text">{fmt(ranking.stackScore)}</div>
        </div>
        <div>
          <div className="text-text-faint">Own</div>
          <div className="font-semibold text-text">{fmt(ranking.ownershipScore)}</div>
        </div>
      </div>

      {ranking.badges.length > 0 && <SlateRankingBadgeRow badges={ranking.badges} />}
    </button>
  );
}
