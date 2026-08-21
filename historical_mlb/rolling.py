"""Rolling historical feature windows (Milestone 32.0, Part 7).

Windows: last 7 days, last 14 days, last 30 days, season-to-date.
Every function here takes an explicit `target_game_date` and an
explicit list of prior game-log entries (each carrying its OWN date) --
it NEVER reaches out to "today," and it always calls
historical_mlb.leakage.filter_pregame_observations() first, so a caller
cannot accidentally include the target game (or anything after it) in
a rolling window even if the input list wasn't pre-filtered.

Source: MLB Stats API's own gameLog endpoints
(historical_mlb.sources.mlb_stats.fetch_pitcher_game_log /
fetch_batter_game_log, both already live-tested for historical dates --
see this milestone's final report) return one entry per game actually
played, each with its own `date` and a full counting-stat block for
that single game -- exactly what a rolling window needs to sum/average
over. Statcast pitch-level rows (historical_mlb.sources.statcast) are
the source for hard-hit%/barrel%/xwOBA specifically, since MLB Stats
API's own game logs don't carry Statcast metrics.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from historical_mlb.leakage import filter_pregame_observations

WINDOWS = {"last_7d": 7, "last_14d": 14, "last_30d": 30}  # days; season-to-date has no day limit


def _days_between(earlier: str, later: str) -> int:
    from datetime import date
    y1, m1, d1 = (int(x) for x in earlier.split("-"))
    y2, m2, d2 = (int(x) for x in later.split("-"))
    return (date(y2, m2, d2) - date(y1, m1, d1)).days


@dataclass
class RollingHitterStats:
    window: str
    games: int = 0
    pa: int = 0
    ab: int = 0
    hits: int = 0
    singles: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    walks: int = 0
    hbp: int = 0
    sac_fly: int = 0
    strikeouts: int = 0
    stolen_bases: int = 0

    @property
    def total_bases(self) -> int:
        return self.singles + 2 * self.doubles + 3 * self.triples + 4 * self.home_runs

    @property
    def avg(self) -> Optional[float]:
        return round(self.hits / self.ab, 4) if self.ab else None

    @property
    def obp(self) -> Optional[float]:
        denom = self.ab + self.walks + self.hbp + self.sac_fly
        return round((self.hits + self.walks + self.hbp) / denom, 4) if denom else None

    @property
    def slg(self) -> Optional[float]:
        return round(self.total_bases / self.ab, 4) if self.ab else None

    @property
    def iso(self) -> Optional[float]:
        slg, avg = self.slg, self.avg
        return round(slg - avg, 4) if slg is not None and avg is not None else None

    @property
    def woba_proxy(self) -> Optional[float]:
        """Simple linear-weights approximation (documented as a proxy,
        not the official FanGraphs wOBA formula -- consistent with this
        project's existing precedent for approximated wOBA, see
        research/batter_enrichment.py's own documented approximation).
        Uses standard, widely-published static weights rather than
        park/season-adjusted ones."""
        denom = self.ab + self.walks + self.hbp + self.sac_fly
        if not denom:
            return None
        numerator = (
            0.69 * self.walks + 0.72 * self.hbp + 0.89 * self.singles
            + 1.27 * self.doubles + 1.62 * self.triples + 2.10 * self.home_runs
        )
        return round(numerator / denom, 4)

    @property
    def k_rate(self) -> Optional[float]:
        return round(self.strikeouts / self.pa, 4) if self.pa else None

    @property
    def bb_rate(self) -> Optional[float]:
        return round(self.walks / self.pa, 4) if self.pa else None


def build_rolling_hitter_stats(
    game_log_entries: List[dict], target_game_date: str, window_days: Optional[int], window_label: str,
) -> RollingHitterStats:
    """`game_log_entries` -- MLB Stats API gameLog splits, each a dict
    with at least `date` and a `stat` sub-dict (atBats, hits, doubles,
    triples, homeRuns, baseOnBalls, hitByPitch, sacFlies, strikeOuts,
    plateAppearances, stolenBases). Excludes the target game itself and
    anything on/after it (filter_pregame_observations, strict <)."""
    safe_dates = set(filter_pregame_observations([e["date"] for e in game_log_entries], target_game_date))
    result = RollingHitterStats(window=window_label)
    for entry in game_log_entries:
        if entry["date"] not in safe_dates:
            continue
        if window_days is not None and _days_between(entry["date"], target_game_date) > window_days:
            continue
        stat = entry.get("stat", {})
        d, t, hr = int(stat.get("doubles") or 0), int(stat.get("triples") or 0), int(stat.get("homeRuns") or 0)
        hits = int(stat.get("hits") or 0)
        result.games += 1
        result.pa += int(stat.get("plateAppearances") or 0)
        result.ab += int(stat.get("atBats") or 0)
        result.hits += hits
        result.singles += max(hits - d - t - hr, 0)
        result.doubles += d
        result.triples += t
        result.home_runs += hr
        result.walks += int(stat.get("baseOnBalls") or 0)
        result.hbp += int(stat.get("hitByPitch") or 0)
        result.sac_fly += int(stat.get("sacFlies") or 0)
        result.strikeouts += int(stat.get("strikeOuts") or 0)
        result.stolen_bases += int(stat.get("stolenBases") or 0)
    return result


@dataclass
class RollingPitcherStats:
    window: str
    games: int = 0
    outs: int = 0
    batters_faced: int = 0
    strikeouts: int = 0
    walks: int = 0
    hits_allowed: int = 0
    earned_runs: int = 0
    home_runs_allowed: int = 0

    @property
    def innings_pitched(self) -> Optional[float]:
        return round(self.outs / 3, 2) if self.outs else None

    @property
    def era(self) -> Optional[float]:
        ip = self.innings_pitched
        return round((self.earned_runs * 9) / ip, 2) if ip else None

    @property
    def whip(self) -> Optional[float]:
        ip = self.innings_pitched
        return round((self.walks + self.hits_allowed) / ip, 3) if ip else None

    @property
    def k_rate(self) -> Optional[float]:
        return round(self.strikeouts / self.batters_faced, 4) if self.batters_faced else None

    @property
    def bb_rate(self) -> Optional[float]:
        return round(self.walks / self.batters_faced, 4) if self.batters_faced else None


def build_rolling_pitcher_stats(
    game_log_entries: List[dict], target_game_date: str, window_days: Optional[int], window_label: str,
) -> RollingPitcherStats:
    """Same discipline as build_rolling_hitter_stats -- `stat` entries
    from MLB Stats API's pitching gameLog (inningsPitched as baseball
    notation, converted via research.innings, never a naive float())."""
    from research import innings as innings_module

    safe_dates = set(filter_pregame_observations([e["date"] for e in game_log_entries], target_game_date))
    result = RollingPitcherStats(window=window_label)
    for entry in game_log_entries:
        if entry["date"] not in safe_dates:
            continue
        if window_days is not None and _days_between(entry["date"], target_game_date) > window_days:
            continue
        stat = entry.get("stat", {})
        ip_str = stat.get("inningsPitched")
        outs = innings_module.innings_notation_to_outs(ip_str) if ip_str not in (None, "") else 0
        result.games += 1
        result.outs += outs
        result.batters_faced += int(stat.get("battersFaced") or 0)
        result.strikeouts += int(stat.get("strikeOuts") or 0)
        result.walks += int(stat.get("baseOnBalls") or 0)
        result.hits_allowed += int(stat.get("hits") or 0)
        result.earned_runs += int(stat.get("earnedRuns") or 0)
        result.home_runs_allowed += int(stat.get("homeRuns") or 0)
    return result


def aggregate_statcast_rates(pitch_rows: List[dict], player_id_column: str, player_id: str) -> Dict[str, Optional[float]]:
    """Aggregates pitch-level Statcast rows (already pregame-filtered by
    the CALLER via leakage.filter_pregame_observations on game_date --
    this function does not itself check dates, since Statcast rows are
    typically already scoped to a fetched date range) into hard-hit%,
    barrel-proxy%, and mean xwOBA-contribution for one player.
    Hard-hit% (>=95mph exit velo) and the barrel proxy (Statcast's own
    published launch_speed/launch_angle "barrel zone" heuristic
    approximated by 98+mph and 26-30 degree launch angle -- documented
    as an approximation of MLB's own undisclosed exact barrel
    classification, consistent with this project's existing
    barrel-rate-approximation precedent elsewhere in the codebase)."""
    batted_balls = [r for r in pitch_rows if r.get(player_id_column) == str(player_id) and r.get("launch_speed") not in (None, "")]
    if not batted_balls:
        return {"hard_hit_rate": None, "barrel_rate_proxy": None, "avg_xwoba_contribution": None, "batted_ball_events": 0}

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    speeds = [_f(r.get("launch_speed")) for r in batted_balls]
    angles = [_f(r.get("launch_angle")) for r in batted_balls]
    xwobas = [_f(r.get("estimated_woba_using_speedangle")) for r in batted_balls if r.get("estimated_woba_using_speedangle") not in (None, "")]

    hard_hit = sum(1 for s in speeds if s is not None and s >= 95)
    barrels = sum(1 for s, a in zip(speeds, angles) if s is not None and a is not None and s >= 98 and 26 <= a <= 30)

    return {
        "hard_hit_rate": round(hard_hit / len(batted_balls), 4),
        "barrel_rate_proxy": round(barrels / len(batted_balls), 4),
        "avg_xwoba_contribution": round(sum(xwobas) / len(xwobas), 4) if xwobas else None,
        "batted_ball_events": len(batted_balls),
    }
