"""Milestone 32.1 -- one pitcher-game feature row (Parts 2, 10, 11, 13,
15, 16, 18). Pure function of already-fetched inputs -- no network
calls here (fully fixture-testable); mirrors hitter_features.py's
design exactly.
"""

from typing import Dict, List, Optional

from evaluation.dk_actual_scoring import calculate_actual_dk_points
from historical_mlb.leakage import filter_pregame_observations
from historical_mlb.rolling import aggregate_statcast_rates, build_rolling_pitcher_stats, days_between
from historical_mlb.scoring import pitcher_result_from_boxscore_entry
from historical_mlb.statcast_aggregation import opponent_offense_aggregate, pitcher_platoon_splits_allowed
from research import innings as innings_module

_ROLLING_WINDOWS = [("7d", 7), ("14d", 14), ("30d", 30), ("season", None)]
_STATCAST_WINDOWS = [("14d", 14), ("30d", 30), ("season", None)]
_PITCHER_ROLLING_STATS = ["outs", "bf", "so", "bb", "h", "hr", "er", "pitch_count"]


def _previous_start(season_game_log: List[dict], target_game_date: str) -> Optional[dict]:
    """Most recent PRIOR appearance strictly before target_game_date --
    used for days_rest and previous_start_pitch_count. Same-day always
    excluded (Part 24)."""
    prior = sorted(
        (e for e in season_game_log if e.get("date") and e["date"] < target_game_date),
        key=lambda e: e["date"],
    )
    return prior[-1] if prior else None


def build_pitcher_game_row(
    *,
    game_pk: int, game_date: str, game_number: int, player_id: str, player_name: str,
    team: str, opponent: str, home_away: str, game_start_time: Optional[str], venue_id: Optional[int],
    bat_hand: Optional[str], throw_hand: Optional[str],
    boxscore_entry: dict, starter_flag: bool,
    season_game_log: List[dict],
    statcast_window_rows: List[dict],
    opponent_season_offense: Dict[str, Optional[float]],
    weather: Optional[dict], venue_roof_type: Optional[str],
) -> Dict:
    row: Dict = {
        "season": int(game_date[:4]), "game_date": game_date, "game_pk": game_pk, "game_number": game_number,
        "player_id": str(player_id), "player_name": player_name, "team": team, "opponent": opponent,
        "home_away": home_away, "game_start_time": game_start_time, "venue_id": venue_id,
        "bat_hand": bat_hand, "throw_hand": throw_hand,
    }

    for label, days in _ROLLING_WINDOWS:
        stats = build_rolling_pitcher_stats(season_game_log, target_game_date=game_date, window_days=days, window_label=label)
        row[f"rolling_outs_{label}"] = stats.outs
        row[f"rolling_ip_{label}"] = stats.innings_pitched
        row[f"rolling_bf_{label}"] = stats.batters_faced
        row[f"rolling_so_{label}"] = stats.strikeouts
        row[f"rolling_bb_{label}"] = stats.walks
        row[f"rolling_h_{label}"] = stats.hits_allowed
        row[f"rolling_hr_{label}"] = stats.home_runs_allowed
        row[f"rolling_er_{label}"] = stats.earned_runs
        row[f"rolling_pitch_count_{label}"] = stats.pitch_count
        row[f"rolling_k_pct_{label}"] = stats.k_rate
        row[f"rolling_bb_pct_{label}"] = stats.bb_rate
        row[f"rolling_k_minus_bb_pct_{label}"] = round(stats.k_rate - stats.bb_rate, 4) if stats.k_rate is not None and stats.bb_rate is not None else None
        row[f"rolling_era_{label}"] = stats.era
        row[f"rolling_whip_{label}"] = stats.whip
        row[f"rolling_hr_rate_{label}"] = round(stats.home_runs_allowed / stats.batters_faced, 4) if stats.batters_faced else None
        row[f"rolling_starts_{label}"] = stats.games

    previous = _previous_start(season_game_log, game_date)
    row["days_rest"] = days_between(previous["date"], game_date) if previous else None
    row["previous_start_pitch_count"] = (previous or {}).get("stat", {}).get("numberOfPitches") if previous else None
    starts_30d = build_rolling_pitcher_stats(season_game_log, target_game_date=game_date, window_days=30, window_label="starts_30d")
    row["starts_last_30d"] = starts_30d.games
    row["innings_last_30d"] = starts_30d.innings_pitched

    for label, days in _STATCAST_WINDOWS:
        safe_dates = set(filter_pregame_observations(sorted({r.get("game_date") for r in statcast_window_rows if r.get("game_date")}), game_date))
        if days is not None:
            safe_dates = {d for d in safe_dates if days_between(d, game_date) <= days}
        window_rows = [r for r in statcast_window_rows if r.get("game_date") in safe_dates]
        agg = aggregate_statcast_rates(window_rows, "pitcher", player_id)
        row[f"statcast_avg_exit_velocity_allowed_{label}"] = agg["avg_exit_velocity"]
        row[f"statcast_avg_launch_angle_allowed_{label}"] = agg["avg_launch_angle"]
        row[f"statcast_hard_hit_rate_allowed_{label}"] = agg["hard_hit_rate"]
        row[f"statcast_barrel_rate_allowed_{label}"] = agg["barrel_rate_proxy"]
        row[f"statcast_xwoba_allowed_{label}"] = agg["avg_xwoba_contribution"]
        row[f"statcast_xslg_allowed_{label}"] = agg["xslg"]
        row[f"statcast_batted_balls_allowed_{label}"] = agg["batted_ball_events"]

    platoon = pitcher_platoon_splits_allowed(statcast_window_rows, player_id)
    for side in ("vs_lhb", "vs_rhb"):
        row[f"platoon_{side}_bf"] = platoon[side]["pa"]
        row[f"platoon_{side}_avg_allowed"] = platoon[side]["avg"]
        row[f"platoon_{side}_obp_allowed"] = platoon[side]["obp"]
        row[f"platoon_{side}_slg_allowed"] = platoon[side]["slg"]
        row[f"platoon_{side}_woba_allowed"] = platoon[side]["woba"]

    row["starter_flag"] = starter_flag
    row["opponent_k_pct_season"] = opponent_season_offense.get("k_pct")
    row["opponent_bb_pct_season"] = opponent_season_offense.get("bb_pct")
    row["opponent_hr_rate_season"] = opponent_season_offense.get("hr_rate")
    row["opponent_woba_season"] = opponent_season_offense.get("woba")
    row["opponent_sample_games"] = opponent_season_offense.get("sample_games")

    row["weather_available"] = weather is not None
    row["weather_source"] = "open_meteo" if weather is not None else None
    row["weather_temperature_f"] = (weather or {}).get("temperature_2m")
    row["weather_wind_speed_mph"] = (weather or {}).get("wind_speed_10m")
    row["weather_wind_direction_deg"] = (weather or {}).get("wind_direction_10m")
    row["weather_precipitation"] = (weather or {}).get("precipitation")
    row["weather_humidity_pct"] = (weather or {}).get("relative_humidity_2m")
    row["venue_roof_type"] = venue_roof_type

    row["draftkings_salary"] = None
    row["vegas_moneyline"] = None
    row["vegas_total"] = None

    result = pitcher_result_from_boxscore_entry(boxscore_entry, game_id=str(game_pk), game_date=game_date)
    scored = calculate_actual_dk_points(result)
    quality_start = bool(result.outs is not None and result.outs >= 18 and (result.earned_runs or 0) <= 3)
    row["actual_outs_recorded"] = result.outs
    row["actual_ip_display"] = innings_module.outs_to_innings_notation(result.outs or 0)
    row["actual_bf"] = result.batters_faced
    row["actual_h"] = result.hits_allowed
    row["actual_hr"] = result.home_runs_allowed
    row["actual_bb"] = result.walks
    row["actual_hbp"] = result.hit_batsmen
    row["actual_so"] = result.strikeouts
    row["actual_er"] = result.earned_runs
    row["actual_pitch_count"] = boxscore_entry.get("stat", {}).get("numberOfPitches")
    row["actual_strikes"] = boxscore_entry.get("stat", {}).get("strikes")
    row["actual_win"] = result.win
    row["actual_loss"] = result.loss
    row["actual_quality_start"] = quality_start
    row["actual_complete_game"] = result.complete_game
    row["actual_shutout"] = result.shutout
    row["actual_dk_points"] = scored["dfs_points"]
    return row
