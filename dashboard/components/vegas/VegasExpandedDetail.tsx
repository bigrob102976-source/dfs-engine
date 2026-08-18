import Link from "next/link";

import { AIInsightBadge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/Header";
import { averageBullpenStrength } from "@/lib/environmentSortFilter";
import { buildVegasAiSummary, firstObservedImpliedRuns, type VegasGameRow } from "@/lib/vegasIntelligence";
import type { BookLineSnapshot, VegasSlateAnalysis, VegasSnapshot } from "@/lib/gameEnvironment";

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

function fmtMl(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return value > 0 ? `+${value}` : `${value}`;
}

function fmtPct(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : `${(value * 100).toFixed(1)}%`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Per-sportsbook Moneyline/Total/Run Line/Last Updated table -- real
 * SportsGameOdds provider data only (Milestone 24). Only the books the
 * API actually returned are shown; nothing is fabricated for a book
 * that didn't post a line. */
function BookTable({ books, homeTeam, awayTeam }: { books: BookLineSnapshot[]; homeTeam: string; awayTeam: string }) {
  if (books.length === 0) {
    return <p className="mb-4 text-text-faint">No individual sportsbook lines were returned by the provider.</p>;
  }
  return (
    <div className="mb-4 overflow-x-auto rounded border border-border-subtle bg-bg-panel-raised p-2.5 text-xs">
      <table className="w-full min-w-[420px]">
        <thead>
          <tr className="text-text-faint">
            <th className="pb-1 text-left font-normal">Book</th>
            <th className="pb-1 text-right font-normal">Moneyline ({awayTeam}/{homeTeam})</th>
            <th className="pb-1 text-right font-normal">Total</th>
            <th className="pb-1 text-right font-normal">Run Line ({homeTeam})</th>
            <th className="pb-1 text-right font-normal">Last Updated</th>
          </tr>
        </thead>
        <tbody className="text-text">
          {books.map((b) => (
            <tr key={b.book} className="border-t border-border-subtle/60">
              <td className="py-1 text-text-muted">{b.book}</td>
              <td className="py-1 text-right">
                {fmtMl(b.away_moneyline)} / {fmtMl(b.home_moneyline)}
              </td>
              <td className="py-1 text-right">{fmt(b.total)}</td>
              <td className="py-1 text-right">{b.home_run_line !== null ? fmt(b.home_run_line) : "--"}</td>
              <td className="py-1 text-right text-text-faint">{fmtTime(b.last_updated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Market-consensus summary (median total, no-vig win probabilities,
 * run-line-derived implied runs) -- see research/game_environment/providers/consensus.py
 * and implied_runs.py for the exact methodology used to compute these. */
function ConsensusSummary({ vegas, homeTeam, awayTeam }: { vegas: VegasSnapshot; homeTeam: string; awayTeam: string }) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 rounded border border-border-subtle bg-bg-panel-raised p-2.5 text-text-muted">
      <span>
        Consensus Total: <span className="text-text">{fmt(vegas.current_home.total)}</span>
      </span>
      <span>
        Books Used: <span className="text-text">{vegas.books_used.length > 0 ? vegas.books_used.join(", ") : "--"}</span>
      </span>
      <span>
        {homeTeam} Win %: <span className="text-text">{fmtPct(vegas.consensus_home_win_probability)}</span>
      </span>
      <span>
        {awayTeam} Win %: <span className="text-text">{fmtPct(vegas.consensus_away_win_probability)}</span>
      </span>
      <span>
        {homeTeam} Implied Runs: <span className="text-text">{fmt(vegas.home_implied_runs)}</span>
      </span>
      <span>
        {awayTeam} Implied Runs: <span className="text-text">{fmt(vegas.away_implied_runs)}</span>
      </span>
      {vegas.implied_runs_calculation_method && (
        <span className="col-span-2 text-[11px] text-text-faint">Method: {vegas.implied_runs_calculation_method}</span>
      )}
      {!vegas.implied_runs_is_valid && (
        <span className="col-span-2 text-[11px] text-red">Implied runs failed validation -- see warnings below.</span>
      )}
      {vegas.validation_warnings.length > 0 && (
        <span className="col-span-2 text-[11px] text-red">{vegas.validation_warnings.join("; ")}</span>
      )}
    </div>
  );
}

function OddsColumn({ title, home, away, homeTeam, awayTeam }: {
  title: string;
  home: { moneyline: number | null; run_line: number | null; total: number | null };
  away: { moneyline: number | null; run_line: number | null; total: number | null };
  homeTeam: string;
  awayTeam: string;
}) {
  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised p-2.5 text-xs">
      <div className="mb-1.5 font-semibold text-text">{title}</div>
      <table className="w-full">
        <thead>
          <tr className="text-text-faint">
            <th className="pb-1 text-left font-normal"> </th>
            <th className="pb-1 text-right font-normal">ML</th>
            <th className="pb-1 text-right font-normal">Line</th>
            <th className="pb-1 text-right font-normal">Total</th>
          </tr>
        </thead>
        <tbody className="text-text">
          <tr>
            <td className="py-0.5 text-text-muted">{homeTeam}</td>
            <td className="py-0.5 text-right">{fmtMl(home.moneyline)}</td>
            <td className="py-0.5 text-right">{home.run_line !== null ? fmt(home.run_line) : "--"}</td>
            <td className="py-0.5 text-right">{fmt(home.total)}</td>
          </tr>
          <tr>
            <td className="py-0.5 text-text-muted">{awayTeam}</td>
            <td className="py-0.5 text-right">{fmtMl(away.moneyline)}</td>
            <td className="py-0.5 text-right">{away.run_line !== null ? fmt(away.run_line) : "--"}</td>
            <td className="py-0.5 text-right">{fmt(away.total)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

const FUTURE_PLACEHOLDERS = ["Public %", "Sharp %", "Bet %", "Steam %", "Closing Line Value"];

/** Full expansion content for one game -- shared by the desktop table's
 * expanded row and the mobile card's expanded section, per Milestone
 * DS3's ROW EXPANSION spec. Every real field comes straight from the
 * immutable Game Environment snapshot or a pure client-side recompute
 * documented in lib/vegasIntelligence.ts; Public %/Sharp %/Bet %/Steam
 * %/Closing Line Value are explicit "Coming Soon" placeholders with no
 * functionality, per the milestone's FUTURE PLACEHOLDERS section. */
export function VegasExpandedDetail({
  row,
  analysis,
  marketView = "pregame",
}: {
  row: VegasGameRow;
  analysis: VegasSlateAnalysis | null;
  marketView?: "pregame" | "live";
}) {
  const { game, homePitcher, awayPitcher } = row;
  const vegas = game.vegas;
  const bullpenStrength = averageBullpenStrength(game);
  const aiSummary = buildVegasAiSummary(game, analysis);
  const firstObserved = vegas ? firstObservedImpliedRuns(vegas) : { home: null, away: null };
  // Milestone 25: only on the PREGAME DFS tab is `vegas` potentially a
  // frozen/zero-contribution value distinct from the real current
  // market -- on the LIVE MARKET tab `vegas` already IS the current
  // market, so showing this comparison again would be redundant.
  const vegasLive = game.vegas_live ?? null;
  const showLiveComparison = marketView === "pregame" && vegasLive != null && vegasLive.game_status !== "PREGAME";

  return (
    <div className="grid grid-cols-1 gap-4 p-4 text-xs lg:grid-cols-2">
      <div>
        <SectionHeader title="AI Summary" />
        <div className="mb-4 flex flex-col gap-1.5">
          {aiSummary.map((b, i) => (
            <AIInsightBadge key={i}>{b}</AIInsightBadge>
          ))}
        </div>

        {vegas ? (
          <>
            {showLiveComparison && vegasLive && (
              <>
                <SectionHeader title="Pregame Lock" />
                <div className="mb-4 grid grid-cols-2 gap-2">
                  <OddsColumn
                    title={vegas.is_frozen_pregame ? "Pregame Projection Market (Frozen)" : "Pregame Projection Market"}
                    home={vegas.current_home}
                    away={vegas.current_away}
                    homeTeam={game.home_team}
                    awayTeam={game.away_team}
                  />
                  <div className="rounded border border-yellow/40 bg-bg-panel-raised p-2.5 text-xs">
                    <div className="mb-1.5 font-semibold text-yellow">Current Market -- IN-PLAY -- NOT USED FOR DFS PROJECTIONS</div>
                    <table className="w-full">
                      <thead>
                        <tr className="text-text-faint">
                          <th className="pb-1 text-left font-normal"> </th>
                          <th className="pb-1 text-right font-normal">ML</th>
                          <th className="pb-1 text-right font-normal">Total</th>
                        </tr>
                      </thead>
                      <tbody className="text-text">
                        <tr>
                          <td className="py-0.5 text-text-muted">{game.home_team}</td>
                          <td className="py-0.5 text-right">{fmtMl(vegasLive.current_home.moneyline)}</td>
                          <td className="py-0.5 text-right">{fmt(vegasLive.current_home.total)}</td>
                        </tr>
                        <tr>
                          <td className="py-0.5 text-text-muted">{game.away_team}</td>
                          <td className="py-0.5 text-right">{fmtMl(vegasLive.current_away.moneyline)}</td>
                          <td className="py-0.5 text-right">{fmt(vegasLive.current_away.total)}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div className="mt-1.5 text-[10px] text-text-faint">MLB Status: {game.mlb_game_status ?? "unknown"}</div>
                  </div>
                </div>
              </>
            )}

            <SectionHeader title="Odds" />
            <div className="mb-4 grid grid-cols-2 gap-2">
              <OddsColumn title="First Observed" home={vegas.opening_home} away={vegas.opening_away} homeTeam={game.home_team} awayTeam={game.away_team} />
              <OddsColumn title="Current" home={vegas.current_home} away={vegas.current_away} homeTeam={game.home_team} awayTeam={game.away_team} />
            </div>

            <SectionHeader title="Betting History" />
            <ol className="mb-4 flex flex-col gap-1 text-text-muted">
              <li>
                <span className="text-text-faint">First Observed{vegas.is_first_pull_of_day ? " (this pull)" : ""}</span> -- Total{" "}
                {fmt(vegas.opening_home.total)}, {game.home_team} ML {fmtMl(vegas.opening_home.moneyline)}, Implied {fmt(firstObserved.home)} /{" "}
                {fmt(firstObserved.away)}
              </li>
              <li>
                <span className="text-text-faint">Current</span> -- Total {fmt(vegas.current_home.total)}, {game.home_team} ML {fmtMl(vegas.current_home.moneyline)}
                , Implied {fmt(vegas.home_implied_runs)} / {fmt(vegas.away_implied_runs)}
              </li>
            </ol>

            {!vegas.is_mock && (
              <>
                <SectionHeader title="Sportsbook Lines" />
                <BookTable books={vegas.books} homeTeam={game.home_team} awayTeam={game.away_team} />

                <SectionHeader title="Market Consensus" />
                <ConsensusSummary vegas={vegas} homeTeam={game.home_team} awayTeam={game.away_team} />
              </>
            )}
          </>
        ) : (
          <div className="mb-4">
            <p className="text-red">NO VALID PREGAME VEGAS</p>
            <p className="mt-1 text-text-faint">
              No valid pregame market snapshot was ever captured for this game -- Vegas contribution is 0 for Native/AI projections.
              {marketView === "pregame" && vegasLive && vegasLive.game_status !== "PREGAME"
                ? " Live/in-play market data may be available under the Live Market tab, for research only."
                : ""}
            </p>
          </div>
        )}

        <SectionHeader title="Future Data" />
        <div className="mb-4 flex flex-wrap gap-1.5 opacity-60">
          {FUTURE_PLACEHOLDERS.map((label) => (
            <span key={label} className="rounded-full border border-dashed border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-faint">
              {label} -- Coming Soon
            </span>
          ))}
        </div>
      </div>

      <div>
        <SectionHeader title="Pitching Matchup" />
        <div className="mb-4 grid grid-cols-2 gap-2">
          {[
            { team: game.away_team, pitcher: awayPitcher },
            { team: game.home_team, pitcher: homePitcher },
          ].map(({ team, pitcher }) => (
            <div key={team} className="rounded border border-border-subtle bg-bg-panel-raised p-2.5">
              <div className="mb-1 font-semibold text-text">{team}</div>
              {pitcher ? (
                <div className="flex flex-col gap-0.5 text-text-muted">
                  <span className="text-text">{pitcher.name}</span>
                  <span>Projection: {fmt(pitcher.projection)}</span>
                  <span>K Score: {fmt(pitcher.strikeout_score ?? null, 0)}</span>
                </div>
              ) : (
                <span className="text-text-faint">Probable starter not yet available.</span>
              )}
            </div>
          ))}
        </div>

        <SectionHeader title="Weather" />
        {game.weather ? (
          <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-text-muted">
            <span>
              Temp: <span className="text-text">{fmt(game.weather.current.temperature_f, 0)}°F</span>
            </span>
            <span>
              Wind: <span className="text-text">{fmt(game.weather.current.wind_speed_mph, 0)} mph</span>
            </span>
            <span>
              Roof: <span className="text-text">{game.weather.roof_status}</span>
            </span>
            <span>
              Rain: <span className="text-text">{fmt(game.weather.current.rain_percent, 0)}%</span>
            </span>
          </div>
        ) : (
          <p className="mb-4 text-text-faint">Weather is unavailable for this game.</p>
        )}

        <SectionHeader title="Bullpen" />
        <div className="mb-4 grid grid-cols-2 gap-2">
          {[
            { team: game.away_team, profile: game.bullpen_away },
            { team: game.home_team, profile: game.bullpen_home },
          ].map(({ team, profile }) => (
            <div key={team} className="rounded border border-border-subtle bg-bg-panel-raised p-2.5">
              <div className="mb-1 font-semibold text-text">{team}</div>
              {profile ? (
                <div className="flex flex-col gap-0.5 text-text-muted">
                  <span>ERA: {fmt(profile.era)}</span>
                  <span>Fatigue: {profile.estimated_fatigue}</span>
                  <span>Strength: {fmt(profile.strength_score, 0)}</span>
                </div>
              ) : (
                <span className="text-text-faint">Unavailable</span>
              )}
            </div>
          ))}
        </div>
        {bullpenStrength !== null && <p className="mb-4 -mt-2 text-[11px] text-text-faint">Average bullpen strength: {fmt(bullpenStrength, 0)}</p>}

        <SectionHeader title="Park Factor" />
        {game.ballpark ? (
          <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-text-muted">
            <span>
              Venue: <span className="text-text">{game.ballpark.venue_name}</span>
            </span>
            <span>
              Park Factor: <span className="text-text">{fmt(game.ballpark.park_factor, 0)}</span>
            </span>
            <span>
              HR Factor: <span className="text-text">{fmt(game.ballpark.hr_factor, 0)}</span>
            </span>
            <span>
              Roof: <span className="text-text">{game.ballpark.roof}</span>
            </span>
          </div>
        ) : (
          <p className="mb-4 text-text-faint">No ballpark profile for this venue.</p>
        )}

        <SectionHeader title="Player Integration" />
        <div className="flex flex-wrap gap-2">
          <Link href={`/dashboard/hitters?team=${game.home_team}`} className="text-accent hover:text-accent-hover">
            {game.home_team} Top Hitters
          </Link>
          <Link href={`/dashboard/hitters?team=${game.away_team}`} className="text-accent hover:text-accent-hover">
            {game.away_team} Top Hitters
          </Link>
          <Link href={`/dashboard/pitchers?team=${game.home_team}`} className="text-accent hover:text-accent-hover">
            {game.home_team} Pitcher
          </Link>
          <Link href={`/dashboard/pitchers?team=${game.away_team}`} className="text-accent hover:text-accent-hover">
            {game.away_team} Pitcher
          </Link>
          <Link href="/dashboard/stacks" className="text-accent hover:text-accent-hover">
            Stacks
          </Link>
        </div>
      </div>
    </div>
  );
}
