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

M32.7A -- weather is now mapped from the REAL, already-persisted
research/game_environment/ snapshot (Open-Meteo, same provider the
AFTER_LINEUP model's weather_* columns were trained against -- see
historical_mlb/hitter_features.py's identical field semantics) when a
caller supplies one via `weather_snapshot`; see _map_weather_features()
below for the exact per-field mapping and its rationale. Omitting the
argument (or passing a genuinely missing/mock snapshot) preserves the
prior, honest MISSING behavior -- weather_available stays False and
every weather_* feature stays None, never fabricated.
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


_MISSING_WEATHER_FEATURES: Dict[str, object] = {
    "weather_available": False,
    "weather_temperature_f": None,
    "weather_wind_speed_mph": None,
    "weather_wind_direction_deg": None,
    "weather_precipitation": None,
    "weather_humidity_pct": None,
}


def _map_weather_features(weather_snapshot: Optional[dict]) -> Dict[str, object]:
    """Maps ONE game's persisted WeatherSnapshot dict (research/
    game_environment/models.py::WeatherSnapshot.to_dict(), as stored in
    a SlateEnvironmentReport's `games[i]["weather"]`) onto the six
    weather_* columns Hitter Model V1's AFTER_LINEUP feature set
    expects. Every mapping below is a same-semantics rename, never a
    reinterpretation -- verified against historical_mlb/hitter_features.py's
    training-time field definitions (Open-Meteo's own raw hourly
    columns: temperature_2m, wind_speed_10m, wind_direction_10m,
    precipitation, relative_humidity_2m) and
    historical_mlb/manifest.py's documented "at game hour" semantics:

        weather_temperature_f    <- first_pitch.temperature_f
        weather_wind_speed_mph   <- first_pitch.wind_speed_mph
        weather_wind_direction_deg <- first_pitch.wind_direction_degrees
        weather_precipitation    <- first_pitch.precipitation_amount_mm
            (Open-Meteo's raw "precipitation" hourly field is a forecast
            AMOUNT, not a probability -- precipitation_probability_percent
            is a genuinely different signal the model was never trained
            on and is never used here.)
        weather_humidity_pct     <- first_pitch.humidity_percent

    `first_pitch` (not `current`) is used because it is the reading
    OpenMeteoWeatherProvider.get_weather() itself selects for the
    forecast hour nearest this specific game's scheduled start (see
    research/game_environment/weather.py) -- matching "at game hour",
    not "right now" (which could be many hours away from first pitch).

    weather_available mirrors the exact training-time definition
    (`weather is not None`) with one addition this live path needs that
    training never had to consider: a MOCK provider's snapshot (
    `is_mock: true` -- e.g. GAME_ENVIRONMENT_PROVIDER=mock) is treated
    identically to no snapshot at all. Real weather only, never mock,
    never fabricated. A closed-dome/indoor game's snapshot (roof_status
    "dome"/"closed") is left exactly as the existing, real (`is_mock:
    false`) OpenMeteoWeatherProvider already represents it -- a
    documented constant climate-controlled reading, not invented here."""
    if not weather_snapshot or weather_snapshot.get("is_mock", True):
        return dict(_MISSING_WEATHER_FEATURES)

    first_pitch = weather_snapshot.get("first_pitch") or {}
    return {
        "weather_available": True,
        "weather_temperature_f": first_pitch.get("temperature_f"),
        "weather_wind_speed_mph": first_pitch.get("wind_speed_mph"),
        "weather_wind_direction_deg": first_pitch.get("wind_direction_degrees"),
        "weather_precipitation": first_pitch.get("precipitation_amount_mm"),
        "weather_humidity_pct": first_pitch.get("humidity_percent"),
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
    weather_snapshot: Optional[dict] = None,
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
    persisted, never reused across slate refreshes).

    `weather_snapshot` (M32.7A): this GAME's own WeatherSnapshot dict
    (research/game_environment/models.py, already-persisted, real --
    see hitter_shadow_inference.py, which resolves it by game_id from
    the latest SlateEnvironmentReport before calling this function).
    Omitting it (the default, None) is the honest "no weather data
    available yet for this slate" case -- every weather_* feature stays
    None, exactly the prior behavior. See _map_weather_features() above
    for the exact field-by-field mapping."""
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

    # Weather (M32.7A): mapped from the real, already-persisted
    # GameEnvironmentReport when the caller supplies one -- see
    # _map_weather_features() above. Honestly MISSING (never fabricated)
    # when no real snapshot is available yet for this game.
    row.update(_map_weather_features(weather_snapshot))
    row["venue_roof_type"] = venue_roof_type

    return LivePregameHitterFeatureResult(player_id=str(player_id), features=row, warnings=warnings)
