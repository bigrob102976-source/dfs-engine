"use client";

import { AIInsightBadge, EnvironmentScoreBadge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Drawer";
import { SectionHeader } from "@/components/ui/Header";
import type { EnvironmentSections } from "@/lib/environmentDisplaySettings";
import type { GameEnvironmentReport, WeatherReading, WeatherSnapshot } from "@/lib/gameEnvironment";
import { toneBadgeClass, toneLabel, weatherRiskTone } from "@/lib/semanticColor";

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

const READING_POINTS: Array<{ key: keyof Pick<WeatherSnapshot, "current" | "first_pitch" | "mid_game" | "late_game">; label: string }> = [
  { key: "current", label: "Current" },
  { key: "first_pitch", label: "First Pitch" },
  { key: "mid_game", label: "Mid Game" },
  { key: "late_game", label: "Late Game" },
];

function ReadingRow({ label, reading }: { label: string; reading: WeatherReading }) {
  return (
    <tr className="border-b border-border-subtle">
      <td className="py-1 pr-2 text-text-faint">{label}</td>
      <td className="py-1 pr-2 text-right text-text">{fmt(reading.temperature_f, 0)}°F</td>
      <td className="py-1 pr-2 text-right text-text">{fmt(reading.feels_like_f, 0)}°F</td>
      <td className="py-1 pr-2 text-right text-text">
        {fmt(reading.wind_speed_mph, 0)} mph{reading.wind_direction_degrees !== null ? ` @ ${fmt(reading.wind_direction_degrees, 0)}°` : ""}
      </td>
      <td className="py-1 text-right text-text">{fmt(reading.rain_percent, 0)}%</td>
    </tr>
  );
}

/** Full research detail for one game -- Weather, Vegas, Bullpen, Park,
 * Umpire, Travel, AI Summary, and a disabled Future Adjustment preview,
 * per the milestone's Game Detail spec. Sections respect the caller's
 * display preferences (`sections`); Umpire and AI Summary always render
 * since neither has a display toggle. */
export function GameEnvironmentDrawer({
  game,
  sections,
  onClose,
}: {
  game: GameEnvironmentReport | null;
  sections: EnvironmentSections;
  onClose: () => void;
}) {
  if (!game) return null;

  return (
    <Drawer onClose={onClose} ariaLabel={`${game.away_team} at ${game.home_team} game environment detail`} width="w-[560px]">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-base font-semibold text-text">
            {game.away_team} @ {game.home_team}
          </div>
          <div className="text-xs text-text-faint">
            {formatDateTime(game.game_datetime_utc)}
            {game.venue_name ? ` · ${game.venue_name}` : ""}
          </div>
        </div>
        <button onClick={onClose} className="text-text-faint hover:text-text" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        <EnvironmentScoreBadge score={game.environment_score.overall} label="ENVIRONMENT" />
        <EnvironmentScoreBadge score={game.environment_score.hitter} label="HITTER" />
        <EnvironmentScoreBadge score={game.environment_score.pitcher} label="PITCHER" orientation="pitching-high" />
        <EnvironmentScoreBadge score={game.environment_score.stack} label="STACK" />
      </div>

      <SectionHeader title="AI Summary" />
      <div className="mb-4 flex flex-col gap-1.5">
        {game.summary.bullet_points.map((b, i) => (
          <AIInsightBadge key={i}>{b}</AIInsightBadge>
        ))}
      </div>

      {sections.weather && (
        <div className="mb-4">
          <SectionHeader title="Weather" />
          {game.weather ? (
            <>
              <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-text-muted">
                <span>
                  Roof: <span className="text-text">{game.weather.roof_status}</span>
                </span>
                {(() => {
                  const risk = weatherRiskTone(game.weather.weather_risk_percent);
                  return (
                    <span className="flex items-center gap-1.5">
                      Weather Risk:
                      <span className="text-text">{fmt(game.weather.weather_risk_percent, 0)}%</span>
                      {risk && (
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${toneBadgeClass(risk.tone)}`}>
                          {toneLabel(risk.tone)}
                        </span>
                      )}
                      {game.weather.weather_status && <span className="text-text-faint">{game.weather.weather_status}</span>}
                    </span>
                  );
                })()}
                {game.weather.postponement_risk_percent !== null && (
                  <span>
                    Postponement Risk: <span className="text-text">{fmt(game.weather.postponement_risk_percent, 0)}%</span>
                  </span>
                )}
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-text-faint">
                    <th className="py-1 text-left font-normal">Point</th>
                    <th className="py-1 text-right font-normal">Temp</th>
                    <th className="py-1 text-right font-normal">Feels</th>
                    <th className="py-1 text-right font-normal">Wind</th>
                    <th className="py-1 text-right font-normal">Rain</th>
                  </tr>
                </thead>
                <tbody>
                  {READING_POINTS.map((p) => (
                    <ReadingRow key={p.key} label={p.label} reading={game.weather![p.key]} />
                  ))}
                </tbody>
              </table>
              {game.weather_analysis && game.weather_analysis.conclusions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {game.weather_analysis.conclusions.map((c) => (
                    <span key={c.code} className="rounded-full bg-bg-panel-raised px-2 py-0.5 text-[10px] text-text-muted">
                      {c.text}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-xs text-text-faint">Weather is unavailable for this game.</p>
          )}
        </div>
      )}

      {sections.vegas && (
        <div className="mb-4">
          <SectionHeader title="Vegas" />
          {game.vegas ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="text-text-faint">Opening Total</div>
              <div className="text-right text-text">{fmt(game.vegas.opening_home.total)}</div>
              <div className="text-text-faint">Current Total</div>
              <div className="text-right text-text">{fmt(game.vegas.current_home.total)}</div>
              <div className="text-text-faint">Total Movement</div>
              <div className="text-right text-text">{fmt(game.vegas.total_movement)}</div>
              <div className="text-text-faint">{game.home_team} Implied Runs</div>
              <div className="text-right text-text">{fmt(game.vegas.home_implied_runs)}</div>
              <div className="text-text-faint">{game.away_team} Implied Runs</div>
              <div className="text-right text-text">{fmt(game.vegas.away_implied_runs)}</div>
              <div className="text-text-faint">{game.home_team} Moneyline</div>
              <div className="text-right text-text">{fmt(game.vegas.current_home.moneyline, 0)}</div>
              <div className="text-text-faint">{game.away_team} Moneyline</div>
              <div className="text-right text-text">{fmt(game.vegas.current_away.moneyline, 0)}</div>
            </div>
          ) : (
            <p className="text-xs text-text-faint">Vegas lines are unavailable for this game.</p>
          )}
        </div>
      )}

      {sections.bullpen && (
        <div className="mb-4">
          <SectionHeader title="Bullpen" />
          {game.bullpen_home || game.bullpen_away ? (
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: game.home_team, profile: game.bullpen_home },
                { label: game.away_team, profile: game.bullpen_away },
              ].map(({ label, profile }) => (
                <div key={label} className="rounded border border-border-subtle bg-bg-panel-raised p-2 text-xs">
                  <div className="mb-1 font-semibold text-text">{label}</div>
                  {profile ? (
                    <div className="flex flex-col gap-0.5 text-text-muted">
                      <span>ERA: {fmt(profile.era)}</span>
                      <span>FIP: {fmt(profile.fip)}</span>
                      <span>Relievers (3d): {profile.relievers_used_last_3_days ?? "--"}</span>
                      <span>Fatigue: {profile.estimated_fatigue}</span>
                      <span>Closer Available: {profile.closer_available === null ? "--" : profile.closer_available ? "Yes" : "No"}</span>
                      <span>Strength: {fmt(profile.strength_score, 0)}</span>
                    </div>
                  ) : (
                    <span className="text-text-faint">Unavailable</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-faint">Bullpen data is unavailable for this game.</p>
          )}
        </div>
      )}

      {sections.park && (
        <div className="mb-4">
          <SectionHeader title="Park" />
          {game.ballpark ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="text-text-faint">Venue</div>
              <div className="text-right text-text">{game.ballpark.venue_name}</div>
              <div className="text-text-faint">Park Factor</div>
              <div className="text-right text-text">{fmt(game.ballpark.park_factor)}</div>
              <div className="text-text-faint">HR Factor</div>
              <div className="text-right text-text">{fmt(game.ballpark.hr_factor)}</div>
              <div className="text-text-faint">Run Factor</div>
              <div className="text-right text-text">{fmt(game.ballpark.run_factor)}</div>
              <div className="text-text-faint">Altitude</div>
              <div className="text-right text-text">{game.ballpark.altitude_ft} ft</div>
              <div className="text-text-faint">Roof</div>
              <div className="text-right text-text">{game.ballpark.roof}</div>
              <div className="text-text-faint">Surface</div>
              <div className="text-right text-text">{game.ballpark.surface}</div>
            </div>
          ) : (
            <p className="text-xs text-text-faint">No ballpark profile for this venue.</p>
          )}
        </div>
      )}

      <div className="mb-4">
        <SectionHeader title="Umpire" />
        {game.umpire?.status === "KNOWN" ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="text-text-faint">Name</div>
            <div className="text-right text-text">{game.umpire.name ?? "--"}</div>
            <div className="text-text-faint">Tendency</div>
            <div className="text-right text-text">{game.umpire.tendency.replace(/_/g, " ")}</div>
            <div className="text-text-faint">Strike %</div>
            <div className="text-right text-text">{fmt(game.umpire.strike_percent)}</div>
            <div className="text-text-faint">Walk %</div>
            <div className="text-right text-text">{fmt(game.umpire.walk_percent)}</div>
            <div className="text-text-faint">K %</div>
            <div className="text-right text-text">{fmt(game.umpire.k_percent)}</div>
            <div className="text-text-faint">Runs/Game</div>
            <div className="text-right text-text">{fmt(game.umpire.runs_per_game)}</div>
          </div>
        ) : (
          <p className="text-xs text-text-faint">
            UNKNOWN -- no umpire assignment has been researched for this game. Big Money DFS never guesses an umpire.
          </p>
        )}
      </div>

      {sections.travel && (
        <div className="mb-4">
          <SectionHeader title="Travel" />
          <div className="grid grid-cols-2 gap-3">
            {[game.travel_home, game.travel_away].map((profile) =>
              profile ? (
                <div key={profile.team_abbr} className="rounded border border-border-subtle bg-bg-panel-raised p-2 text-xs">
                  <div className="mb-1 font-semibold text-text">{profile.team_abbr}</div>
                  {profile.status === "KNOWN" ? (
                    <div className="flex flex-col gap-0.5 text-text-muted">
                      <span>Distance: {fmt(profile.distance_miles, 0)} mi</span>
                      <span>Timezones Crossed: {profile.timezones_crossed ?? "--"}</span>
                      <span>Back-to-Back: {profile.back_to_back === null ? "UNKNOWN" : profile.back_to_back ? "Yes" : "No"}</span>
                      <span>Getaway Day: {profile.getaway_day === null ? "UNKNOWN" : profile.getaway_day ? "Yes" : "No"}</span>
                    </div>
                  ) : (
                    <span className="text-text-faint">UNKNOWN</span>
                  )}
                </div>
              ) : null,
            )}
          </div>
        </div>
      )}

      <div className="mt-4 border-t border-border-subtle pt-3">
        <SectionHeader title="Future Adjustment Preview" />
        <p className="mb-2 text-[11px] text-text-faint">
          Illustrative only -- disabled until a future milestone wires these into projections. No projection, ownership, or
          optimizer value is affected today.
        </p>
        <div className="flex flex-wrap gap-3 text-xs text-text-faint opacity-60">
          <span>Weather {game.future_adjustment_preview.weather_points !== null ? `+${fmt(game.future_adjustment_preview.weather_points)}` : "--"}</span>
          <span>Vegas {game.future_adjustment_preview.vegas_points !== null ? `+${fmt(game.future_adjustment_preview.vegas_points)}` : "--"}</span>
          <span>Bullpen {game.future_adjustment_preview.bullpen_points !== null ? `+${fmt(game.future_adjustment_preview.bullpen_points)}` : "--"}</span>
          <span className="font-semibold uppercase tracking-wide">Disabled</span>
        </div>
      </div>
    </Drawer>
  );
}
