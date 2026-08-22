"""Milestone 32.1 -- one hitter-game feature row (Parts 2, 9, 12, 14,
16, 17, 20, 21). Pure function of already-fetched inputs -- no network
calls here, so this is fully fixture-testable. The orchestrator
(warehouse_builder.py) is responsible for fetching/caching every input
this function needs and calling it once per hitter per game.
"""

from typing import Dict, List, Optional

from evaluation.dk_actual_scoring import calculate_actual_hitter_dk_points
from historical_mlb.leakage import filter_pregame_observations
from historical_mlb.rolling import aggregate_statcast_rates, build_rolling_hitter_stats, days_between
from historical_mlb.scoring import hitter_result_from_boxscore_entry
from historical_mlb.statcast_aggregation import hitter_platoon_splits

_ROLLING_WINDOWS = [("7d", 7), ("14d", 14), ("30d", 30), ("season", None)]
_STATCAST_WINDOWS = [("14d", 14), ("30d", 30), ("season", None)]
_HITTER_ROLLING_STATS = ["pa", "ab", "h", "1b", "2b", "3b", "hr", "bb", "hbp", "r", "rbi", "sb", "so"]


def build_hitter_game_row(
    *,
    game_pk: int, game_date: str, game_number: int, player_id: str, player_name: str,
    team: str, opponent: str, home_away: str, game_start_time: Optional[str], venue_id: Optional[int],
    bat_hand: Optional[str], throw_hand: Optional[str],
    boxscore_entry: dict,
    season_game_log: List[dict],
    statcast_window_rows: List[dict],
    opposing_starter_id: Optional[str], opposing_starter_hand: Optional[str],
    opposing_starter_season_era: Optional[float], opposing_starter_season_k_pct: Optional[float],
    batting_order_actual: Optional[int], lineup_confirmed: bool,
    weather: Optional[dict], venue_roof_type: Optional[str],
) -> Dict:
    row: Dict = {
        "season": int(game_date[:4]), "game_date": game_date, "game_pk": game_pk, "game_number": game_number,
        "player_id": str(player_id), "player_name": player_name, "team": team, "opponent": opponent,
        "home_away": home_away, "game_start_time": game_start_time, "venue_id": venue_id,
        "bat_hand": bat_hand, "throw_hand": throw_hand,
    }

    # Rolling MLB-Stats-API game-log features (Part 12) -- ALWAYS excludes the target game (leakage.py, strict same-day exclusion per Part 24).
    for label, days in _ROLLING_WINDOWS:
        stats = build_rolling_hitter_stats(season_game_log, target_game_date=game_date, window_days=days, window_label=label)
        for stat in _HITTER_ROLLING_STATS:
            attr = {
                "h": "hits", "1b": "singles", "2b": "doubles", "3b": "triples", "hr": "home_runs",
                "bb": "walks", "r": "runs", "sb": "stolen_bases", "so": "strikeouts",
            }.get(stat, stat)
            row[f"rolling_{stat}_{label}"] = getattr(stats, attr)
        row[f"rolling_avg_{label}"] = stats.avg
        row[f"rolling_obp_{label}"] = stats.obp
        row[f"rolling_slg_{label}"] = stats.slg
        row[f"rolling_ops_{label}"] = round(stats.obp + stats.slg, 4) if stats.obp is not None and stats.slg is not None else None
        row[f"rolling_iso_{label}"] = stats.iso
        row[f"rolling_k_pct_{label}"] = stats.k_rate
        row[f"rolling_bb_pct_{label}"] = stats.bb_rate
        row[f"rolling_hr_per_pa_{label}"] = round(stats.home_runs / stats.pa, 4) if stats.pa else None
        row[f"rolling_sb_per_pa_{label}"] = round(stats.stolen_bases / stats.pa, 4) if stats.pa else None
        row[f"rolling_games_{label}"] = stats.games

    # Statcast individual rates (Part 14) -- statcast_window_rows is
    # ALREADY leakage-safe (caller filters to game_date < target_game_date,
    # same-day always excluded per Part 24) and already scoped to the
    # relevant lookback; this function additionally re-derives each
    # sub-window from the same buffer by date so 14d/30d/season share
    # one fetched buffer, never three separate ones.
    for label, days in _STATCAST_WINDOWS:
        safe_dates = set(filter_pregame_observations(sorted({r.get("game_date") for r in statcast_window_rows if r.get("game_date")}), game_date))
        if days is not None:
            safe_dates = {d for d in safe_dates if days_between(d, game_date) <= days}
        window_rows = [r for r in statcast_window_rows if r.get("game_date") in safe_dates]
        agg = aggregate_statcast_rates(window_rows, "batter", player_id)
        row[f"statcast_avg_exit_velocity_{label}"] = agg["avg_exit_velocity"]
        row[f"statcast_avg_launch_angle_{label}"] = agg["avg_launch_angle"]
        row[f"statcast_hard_hit_rate_{label}"] = agg["hard_hit_rate"]
        row[f"statcast_barrel_rate_{label}"] = agg["barrel_rate_proxy"]
        row[f"statcast_xwoba_{label}"] = agg["avg_xwoba_contribution"]
        row[f"statcast_xslg_{label}"] = agg["xslg"]
        row[f"statcast_batted_balls_{label}"] = agg["batted_ball_events"]

    # Platoon (Part 16) -- trailing window already applied by the
    # caller-supplied statcast_window_rows (documented limitation, see
    # historical_mlb.statcast_aggregation's module docstring).
    platoon = hitter_platoon_splits(statcast_window_rows, player_id)
    for side in ("vs_lhp", "vs_rhp"):
        for stat in ("pa", "avg", "obp", "slg", "woba"):
            row[f"platoon_{side}_{stat}"] = platoon[side][stat]

    # Matchup (Part 17)
    row["opposing_starting_pitcher_id"] = opposing_starter_id
    row["opposing_starting_pitcher_hand"] = opposing_starter_hand
    row["opposing_pitcher_era_season"] = opposing_starter_season_era
    row["opposing_pitcher_k_pct_season"] = opposing_starter_season_k_pct

    # Batting order (Part 21) -- explicit availability gate so a
    # pre-lineup model never reads batting_order_actual by accident.
    row["batting_order_actual"] = batting_order_actual
    row["lineup_availability"] = "confirmed" if lineup_confirmed else "unconfirmed"

    # Weather (Part 20)
    row["weather_available"] = weather is not None
    row["weather_source"] = "open_meteo" if weather is not None else None
    row["weather_temperature_f"] = (weather or {}).get("temperature_2m")
    row["weather_wind_speed_mph"] = (weather or {}).get("wind_speed_10m")
    row["weather_wind_direction_deg"] = (weather or {}).get("wind_direction_10m")
    row["weather_precipitation"] = (weather or {}).get("precipitation")
    row["weather_humidity_pct"] = (weather or {}).get("relative_humidity_2m")
    row["venue_roof_type"] = venue_roof_type

    # Explicitly unavailable-but-schema-present (Parts 25/26) -- never fabricated.
    row["draftkings_salary"] = None
    row["vegas_team_total"] = None

    # Actual outcomes + target (Parts 9, 24 -- target/outcome fields
    # live ONLY in this dict, never fed back as a "feature" -- see
    # quality_gates.py's structural enforcement against the manifest).
    result = hitter_result_from_boxscore_entry(boxscore_entry, game_id=str(game_pk), game_date=game_date)
    scored = calculate_actual_hitter_dk_points(result)
    singles = max((result.hits or 0) - (result.doubles or 0) - (result.triples or 0) - (result.home_runs or 0), 0)
    row["actual_pa"] = result.plate_appearances
    row["actual_ab"] = result.at_bats
    row["actual_h"] = result.hits
    row["actual_1b"] = singles
    row["actual_2b"] = result.doubles
    row["actual_3b"] = result.triples
    row["actual_hr"] = result.home_runs
    row["actual_bb"] = result.walks
    row["actual_hbp"] = result.hit_by_pitch
    row["actual_r"] = result.runs
    row["actual_rbi"] = result.rbi
    row["actual_sb"] = result.stolen_bases
    row["actual_cs"] = boxscore_entry.get("stat", {}).get("caughtStealing")
    row["actual_so"] = result.strikeouts
    row["actual_dk_points"] = scored["dfs_points"]
    return row
