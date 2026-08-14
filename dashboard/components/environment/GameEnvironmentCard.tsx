import { EnvironmentScoreBadge } from "@/components/ui/Badge";
import type { GameEnvironmentReport } from "@/lib/gameEnvironment";
import { averageBullpenStrength } from "@/lib/environmentSortFilter";

function formatGameTime(iso: string | null): string {
  if (!iso) return "Time TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Time TBD";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmt(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

/** Compact summary card for one game's environment research -- Teams,
 * Environment Score, Weather, Vegas, Bullpen, Park, Umpire, Stack Rating,
 * per the milestone's Game Card spec. Clicking opens the full detail
 * drawer (GameEnvironmentDrawer). Umpire always renders (no display
 * toggle); the other four sections respect the caller's section
 * preferences. */
export function GameEnvironmentCard({
  game,
  sections,
  onOpen,
}: {
  game: GameEnvironmentReport;
  sections: { weather: boolean; vegas: boolean; bullpen: boolean; park: boolean };
  onOpen: () => void;
}) {
  const bullpenStrength = averageBullpenStrength(game);
  const weatherHeadline = game.weather_analysis?.conclusions[0]?.text ?? null;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 text-left shadow-[var(--shadow-card)] transition-colors duration-150 hover:border-accent"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-text">
            {game.away_team} @ {game.home_team}
          </div>
          <div className="text-[11px] text-text-faint">
            {formatGameTime(game.game_datetime_utc)}
            {game.venue_name ? ` · ${game.venue_name}` : ""}
          </div>
        </div>
        <EnvironmentScoreBadge score={game.environment_score.overall} label="ENV" />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <EnvironmentScoreBadge score={game.environment_score.hitter} label="HIT" />
        <EnvironmentScoreBadge score={game.environment_score.pitcher} label="PIT" orientation="pitching-high" />
        <EnvironmentScoreBadge score={game.environment_score.stack} label="STACK" />
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        {sections.weather && (
          <div className="text-text-muted">
            <span className="text-text-faint">Weather </span>
            {game.weather ? weatherHeadline ?? "No notable conclusions" : "Unavailable"}
          </div>
        )}
        {sections.vegas && (
          <div className="text-text-muted">
            <span className="text-text-faint">Total </span>
            {game.vegas?.current_home?.total !== null && game.vegas?.current_home?.total !== undefined
              ? fmt(game.vegas.current_home.total, 1)
              : "--"}
          </div>
        )}
        {sections.bullpen && (
          <div className="text-text-muted">
            <span className="text-text-faint">Bullpen </span>
            {fmt(bullpenStrength)}
          </div>
        )}
        {sections.park && (
          <div className="text-text-muted">
            <span className="text-text-faint">Park </span>
            {game.ballpark ? fmt(game.ballpark.park_factor) : "--"}
          </div>
        )}
        <div className="text-text-muted">
          <span className="text-text-faint">Umpire </span>
          {game.umpire?.status === "KNOWN" ? game.umpire.tendency.replace(/_/g, " ") : "UNKNOWN"}
        </div>
      </div>

      {game.summary.bullet_points[0] && <div className="text-[11px] italic text-purple">{game.summary.bullet_points[0]}</div>}
    </button>
  );
}
