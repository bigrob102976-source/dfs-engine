"""Milestone 32.3B -- builds today's pregame HITTER features using the
EXACT SAME feature-computation functions historical_models.hitter_v1
was trained against (historical_mlb.rolling / historical_mlb.
statcast_aggregation), fed by freshly live-fetched data instead of
warehouse parquet rows. Mirrors big_money_ml/live_features.py's
discipline exactly for the hitter side.

This module never redefines a feature's math -- see
hitter_feature_parity.py for the per-column audit proving that. The
frozen Hitter Model V1 uses the AFTER_LINEUP feature set (see M32.3's
own selection), so this module ALWAYS requires a confirmed opposing
starter identity + confirmed batting order -- callers must resolve
those from research_output/<date>/pitchers.json and
research_output/<date>/batters.json BEFORE calling this function (see
hitter_shadow_inference.py); this module never guesses either one.

IMPORTANT -- import boundary: historical_mlb.hitter_features,
historical_mlb.pitcher_features, historical_mlb.scoring, and
historical_mlb.sources.mlb_stats all import evaluation.* at module
scope. This module is part of the LIVE PREGAME path and must never
import evaluation, even transitively (see
tests/test_architecture_separation.py) -- so it imports
research.collector directly and reuses big_money_ml.live_features'
already-evaluation-free helpers (LiveStatcastBuffer,
build_live_statcast_buffer, _unwrap_game_log, _person_handedness) by
import rather than duplicating them a third time.

Weather is deliberately NOT fetched here (see hitter_feature_parity.py
-- MISSING, not fabricated); every weather_* feature is left None.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config.game_environment_config import BALLPARKS
from historical_mlb.rolling import aggregate_statcast_rates, build_rolling_hitter_stats, build_rolling_pitcher_stats, days_between
from historical_mlb.statcast_aggregation import hitter_platoon_splits
from research.collector import fetch_batter_game_log, fetch_person, fetch_pitcher_game_log

from big_money_ml.live_features import LiveStatcastBuffer, _person_handedness, _unwrap_game_log

_ROLLING_WINDOWS = [("7d", 7), ("14d", 14), ("30d", 30), ("season", None)]
_STATCAST_WINDOWS = [("14d", 14), ("30d", 30), ("season", None)]
_HITTER_ROLLING_STATS = ["pa", "ab", "h", "1b", "2b", "3b", "hr", "bb", "hbp", "r", "rbi", "sb", "so"]

_ROLLING_ATTR_BY_STAT = {
    "h": "hits", "1b": "singles", "2b": "doubles", "3b": "triples", "hr": "home_runs",
    "bb": "walks", "r": "runs", "sb": "stolen_bases", "so": "strikeouts",
}


@dataclass
class LivePregameHitterFeatureResult:
    player_id: str
    features: Dict
    warnings: List[str] = field(default_factory=list)


def build_live_pregame_hitter_features(
    *,
    player_id: str,
    team: str,
    opponent: str,
    home_away: str,
    as_of_date: str,
    venue_id: Optional[int],
    statcast_buffer: LiveStatcastBuffer,
    opposing_starter_id: str,
    batting_order_actual: int,
    opposing_pitcher_cache: Optional[Dict[str, dict]] = None,
) -> LivePregameHitterFeatureResult:
    """Mirrors historical_mlb.hitter_features.build_hitter_game_row's
    PREGAME portion exactly (same sub-function calls, same argument
    order), but never requires a boxscore_entry. AFTER_LINEUP-only:
    callers must supply an already-confirmed opposing_starter_id and
    batting_order_actual (see eligible_hitters.py / hitter_shadow_
    inference.py) -- this function does not decide eligibility, it
    only computes features once eligibility is already established.

    Milestone 32.4 performance optimization -- `opposing_pitcher_cache`
    is an OPTIONAL shared dict a caller running many hitters in one
    slate refresh (hitter_shadow_inference.py) may pass in so that
    hitters facing the SAME opposing starter (up to 8-9 per game) reuse
    one fetch_person/fetch_pitcher_game_log result instead of refetching
    it once per hitter. `as_of_date` is constant across one slate run,
    so caching purely by opposing_starter_id is safe within that scope.
    Omitting it (the default) preserves the exact prior always-fetch
    behavior -- purely additive, never weakens data freshness (the cache
    only ever lives for the duration of one Python process's run, never
    persisted, never reused across slate refreshes)."""
    warnings: List[str] = []
    season = as_of_date[:4]

    season_game_log = _unwrap_game_log(fetch_batter_game_log(player_id, season))
    if not season_game_log:
        warnings.append(f"No current-season game log for player {player_id} -- rolling_* features will be None (first game of the season, or genuinely no data).")

    statcast_rows = statcast_buffer.rows()

    person = fetch_person(player_id)
    handedness = _person_handedness(person)
    if handedness.get("bat_side") is None:
        warnings.append(f"No bat_side available from MLB Stats API for player {player_id}.")

    home_team = team if home_away == "home" else opponent
    venue_roof_type = (BALLPARKS.get(home_team) or {}).get("roof")

    row: Dict = {
        "team": team, "opponent": opponent, "home_away": home_away, "venue_id": venue_id,
        "bat_hand": handedness.get("bat_side"), "throw_hand": handedness.get("throw_hand"),
    }

    for label, days in _ROLLING_WINDOWS:
        stats = build_rolling_hitter_stats(season_game_log, target_game_date=as_of_date, window_days=days, window_label=label)
        for stat in _HITTER_ROLLING_STATS:
            attr = _ROLLING_ATTR_BY_STAT.get(stat, stat)
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

    for label, days in _STATCAST_WINDOWS:
        if days is not None:
            window_rows = [r for r in statcast_rows if r.get("game_date") and days_between(r["game_date"], as_of_date) <= days]
        else:
            window_rows = statcast_rows
        agg = aggregate_statcast_rates(window_rows, "batter", player_id)
        row[f"statcast_avg_exit_velocity_{label}"] = agg["avg_exit_velocity"]
        row[f"statcast_avg_launch_angle_{label}"] = agg["avg_launch_angle"]
        row[f"statcast_hard_hit_rate_{label}"] = agg["hard_hit_rate"]
        row[f"statcast_barrel_rate_{label}"] = agg["barrel_rate_proxy"]
        row[f"statcast_xwoba_{label}"] = agg["avg_xwoba_contribution"]
        row[f"statcast_xslg_{label}"] = agg["xslg"]
        row[f"statcast_batted_balls_{label}"] = agg["batted_ball_events"]

    platoon = hitter_platoon_splits(statcast_rows, player_id)
    for side in ("vs_lhp", "vs_rhp"):
        for stat in ("pa", "avg", "obp", "slg", "woba"):
            row[f"platoon_{side}_{stat}"] = platoon[side][stat]

    cache = opposing_pitcher_cache if opposing_pitcher_cache is not None else {}
    cached = cache.get(opposing_starter_id)
    if cached is None:
        opposing_person = fetch_person(opposing_starter_id)
        opposing_hand = (_person_handedness(opposing_person) or {}).get("throw_hand")
        opposing_season_log = _unwrap_game_log(fetch_pitcher_game_log(opposing_starter_id, season))
        opposing_season_stats = build_rolling_pitcher_stats(opposing_season_log, target_game_date=as_of_date, window_days=None, window_label="season")
        cached = {
            "hand": opposing_hand, "era": opposing_season_stats.era, "k_pct": opposing_season_stats.k_rate,
            "has_season_log": bool(opposing_season_log),
        }
        cache[opposing_starter_id] = cached

    if cached["hand"] is None:
        warnings.append(f"No throw_hand available from MLB Stats API for opposing starter {opposing_starter_id}.")
    if not cached["has_season_log"]:
        warnings.append(f"No current-season game log for opposing starter {opposing_starter_id} -- opposing_pitcher_era_season/k_pct_season will be None.")

    row["opposing_starting_pitcher_hand"] = cached["hand"]
    row["opposing_pitcher_era_season"] = cached["era"]
    row["opposing_pitcher_k_pct_season"] = cached["k_pct"]

    row["batting_order_actual"] = batting_order_actual

    # Weather: MISSING in live V1 (see hitter_feature_parity.py) -- never fabricated.
    row["weather_available"] = False
    row["weather_temperature_f"] = None
    row["weather_wind_speed_mph"] = None
    row["weather_wind_direction_deg"] = None
    row["weather_precipitation"] = None
    row["weather_humidity_pct"] = None
    row["venue_roof_type"] = venue_roof_type

    return LivePregameHitterFeatureResult(player_id=str(player_id), features=row, warnings=warnings)
