"""Milestone 32.3B -- training/live feature parity audit for the frozen
HITTER model (feature_availability_class == "AFTER_LINEUP", per M32.3's
own selection). Mirrors big_money_ml/feature_parity.py's discipline
exactly: every EXACT/COMPATIBLE row is produced by calling the literal
training-time function with live-fetched inputs instead of warehouse
inputs -- see live_hitter_features.py.
"""

from dataclasses import dataclass
from typing import List

from historical_models.hitter_v1.features import AFTER_LINEUP_FEATURE_COLUMNS, _family_of

EXACT = "EXACT"
COMPATIBLE = "COMPATIBLE"
MISSING = "MISSING"
INCOMPATIBLE = "INCOMPATIBLE"


@dataclass
class FeatureParityRow:
    feature: str
    training_definition: str
    historical_source: str
    live_source: str
    live_availability: str
    transformation: str
    parity_status: str


_FAMILY_PARITY = {
    "rolling": FeatureParityRow(
        feature="rolling_*", training_definition="Trailing 7d/14d/30d/season-to-date hitting totals from MLB Stats API gameLog entries, aggregated by historical_mlb.rolling.build_rolling_hitter_stats.",
        historical_source="historical_mlb.sources.mlb_stats.fetch_cached_season_game_log (re-exports research.collector.fetch_batter_game_log verbatim)",
        live_source="research.collector.fetch_batter_game_log, called directly for the CURRENT season (same evaluation-free unwrapping helper as the pitcher live path).",
        live_availability="Available for any hitter with at least one current-season MLB plate appearance; empty (not fabricated) for a rookie's first game.",
        transformation="None -- historical_mlb.rolling.build_rolling_hitter_stats is called directly, unmodified.",
        parity_status=EXACT,
    ),
    "statcast": FeatureParityRow(
        feature="statcast_*_14d / statcast_*_30d / statcast_*_season",
        training_definition="Trailing 14d/30d/30d-buffer-capped-\"season\" Statcast batted-ball aggregates (hard-hit%, barrel-rate proxy, xwOBA, xSLG, exit velocity, launch angle) via historical_mlb.rolling.aggregate_statcast_rates(mode=\"batter\"). NOTE: the training warehouse's own STATCAST_BUFFER_DAYS=30 means \"_season\" here is ALSO only a trailing-30-day proxy -- same documented limitation as the pitcher model.",
        historical_source="historical_mlb.warehouse_builder.StatcastBuffer, fed by historical_mlb.sources.statcast.fetch_cached_statcast_csv_text (Baseball Savant CSV search).",
        live_source="The SAME live-tested LiveStatcastBuffer pattern already built for pitcher shadow inference (big_money_ml.live_features), advanced through the trailing 30 real calendar days.",
        live_availability="Available for any hitter with at least one batted-ball event in the trailing 30 days.",
        transformation="None.",
        parity_status=EXACT,
    ),
    "platoon": FeatureParityRow(
        feature="platoon_vs_lhp_* / platoon_vs_rhp_*",
        training_definition="historical_mlb.statcast_aggregation.hitter_platoon_splits over the same Statcast window buffer.",
        historical_source="Same StatcastBuffer as statcast_*.",
        live_source="Same StatcastBuffer as statcast_* (live).",
        live_availability="Available whenever the hitter faced at least one pitcher of that hand in the trailing 30 days.",
        transformation="None.",
        parity_status=EXACT,
    ),
    "opposing_pitcher": FeatureParityRow(
        feature="opposing_starting_pitcher_hand / opposing_pitcher_era_season / opposing_pitcher_k_pct_season",
        training_definition="The opposing team's actual game starter (identified from that SAME game's own postgame boxscore in training, since historical dates already know who started) -- hand from the identity crosswalk, ERA/K% from historical_mlb.rolling.build_rolling_pitcher_stats(window_days=None) over that pitcher's season game log.",
        historical_source="historical_mlb.warehouse_builder's boxscore-derived starter identification + season game log.",
        live_source="The opposing team's MLB Stats API PROBABLE starting pitcher (research_output/<date>/pitchers.json / games.json's home_probable_pitcher_id/away_probable_pitcher_id -- the same probable-starter field the M32.2B pitcher shadow path already treats as authoritative) for hand; historical_mlb.rolling.build_rolling_pitcher_stats over that pitcher's LIVE current-season game log for ERA/K%.",
        live_availability="Available whenever both teams' probable starters are announced for the slate (standard well before lineups post).",
        transformation="Training identifies the starter from a completed game's own boxscore; live identifies the PROBABLE starter pregame. These are the same real-world concept (who started/is starting this game) captured at two different, both-legitimate points -- probable-starter scratches are rare and this is the only pregame-available equivalent.",
        parity_status=EXACT,
    ),
    "lineup": FeatureParityRow(
        feature="batting_order_actual",
        training_definition="The boxscore's own battingOrder field for the confirmed lineup slot the hitter actually batted in.",
        historical_source="MLB Stats API boxscore (postgame, but reflects the pregame-locked lineup).",
        live_source="research_output/<date>/batters.json's own batting_order field -- already fetched by the existing live research pipeline for every posted-lineup hitter (status == \"starting_lineup\"), independent of this milestone.",
        live_availability="Available only once that team's lineup has posted -- exactly the AFTER_LINEUP gate this feature set exists to enforce; unconfirmed-lineup hitters are excluded from ML-eligibility entirely before this feature is ever needed (see eligible_hitters.py).",
        transformation="None -- read directly, never inferred/guessed.",
        parity_status=EXACT,
    ),
    "weather": FeatureParityRow(
        feature="weather_available / weather_temperature_f / weather_wind_speed_mph / weather_wind_direction_deg / weather_precipitation / weather_humidity_pct",
        training_definition="Open-Meteo HISTORICAL ARCHIVE hourly weather at the home team's approximate coordinates.",
        historical_source="historical_mlb.sources.weather.fetch_cached_weather_json (archive endpoint) -- 0% missing across all 101,594 training rows.",
        live_source="research.game_environment.storage.load_latest_environment_report's real, live Open-Meteo FORECAST weather (research/game_environment/weather.py::OpenMeteoWeatherProvider -- the SAME provider, not the archive endpoint, since a pregame slate has no archive data yet), resolved by game_id and mapped by big_money_ml.live_hitter_features._map_weather_features (M32.7A). Uses the first_pitch reading -- the forecast hour nearest this game's scheduled start.",
        live_availability="Available once an admin Refresh Data run has generated today's Game Environment snapshot (scripts/build_game_environment_report.py) AND the provider is the real (non-mock) one. Honestly None/False -- never fabricated -- when no snapshot exists yet, or the configured provider is mock (GAME_ENVIRONMENT_PROVIDER=mock).",
        transformation="Field rename + reading selection only (first_pitch's temperature_f/wind_speed_mph/wind_direction_degrees/precipitation_amount_mm/humidity_percent -> weather_temperature_f/weather_wind_speed_mph/weather_wind_direction_deg/weather_precipitation/weather_humidity_pct) -- no unit conversion or value transformation (both the historical archive fetch and the live forecast fetch already return Fahrenheit/mph/degrees/mm/percent).",
        parity_status=EXACT,
    ),
    "venue": FeatureParityRow(
        feature="team / venue_id / home_away",
        training_definition="Identity fields carried straight through from the game/lineup join -- not statistics.",
        historical_source="historical_mlb.game_universe / crosswalk join.",
        live_source="research_output/<date>/games.json + the eligible hitter's own team from the DK player pool's M30.1 eligibility join.",
        live_availability="Always available for any hitter the eligibility layer already resolved to a game.",
        transformation="None -- identity passthrough.",
        parity_status=EXACT,
    ),
    "core": FeatureParityRow(
        feature="opponent",
        training_definition="Opponent team abbreviation, carried straight through from the game/lineup join.",
        historical_source="historical_mlb.game_universe / crosswalk join.",
        live_source="research_output/<date>/games.json + the eligible hitter's own opponent from the DK player pool's M30.1 eligibility join.",
        live_availability="Always available for any hitter the eligibility layer already resolved to a game.",
        transformation="None -- identity passthrough.",
        parity_status=EXACT,
    ),
    "handedness": FeatureParityRow(
        feature="bat_hand / throw_hand",
        training_definition="historical_mlb.sources.mlb_stats.person_handedness(fetch_person(player_id)) -- MLB Stats API /people/{id}.",
        historical_source="research.collector.fetch_person, re-exported verbatim by historical_mlb.sources.mlb_stats.",
        live_source="The SAME research.collector.fetch_person function, called live (same helper already built for pitcher shadow inference).",
        live_availability="Available for any player MLB Stats API has bio data for.",
        transformation="None.",
        parity_status=EXACT,
    ),
}

_COLUMN_OVERRIDES = {
    "venue_roof_type": FeatureParityRow(
        feature="venue_roof_type", training_definition="config.game_environment_config.BALLPARKS[home_team][\"roof\"] -- a static reference table, never computed from game-level data.",
        historical_source="config.game_environment_config.BALLPARKS (static).",
        live_source="config.game_environment_config.BALLPARKS (static) -- the exact same table, imported directly, never duplicated.",
        live_availability="Always available for any recognized home team.",
        transformation="None.",
        parity_status=EXACT,
    ),
}


def build_hitter_feature_parity_report() -> List[FeatureParityRow]:
    """One row per AFTER_LINEUP_FEATURE_COLUMNS entry (the frozen M32.3
    model's own schema), each stamped with its exact column name."""
    rows: List[FeatureParityRow] = []
    for column in AFTER_LINEUP_FEATURE_COLUMNS:
        if column in _COLUMN_OVERRIDES:
            rows.append(_COLUMN_OVERRIDES[column])
            continue
        family = _family_of(column)
        template = _FAMILY_PARITY.get(family)
        if template is None:
            rows.append(FeatureParityRow(
                feature=column, training_definition="unclassified", historical_source="unknown",
                live_source="unknown", live_availability="unknown", transformation="unknown",
                parity_status=INCOMPATIBLE,
            ))
            continue
        rows.append(FeatureParityRow(
            feature=column, training_definition=template.training_definition,
            historical_source=template.historical_source, live_source=template.live_source,
            live_availability=template.live_availability, transformation=template.transformation,
            parity_status=template.parity_status,
        ))
    return rows


def summarize_hitter_parity(rows: List[FeatureParityRow]) -> dict:
    total = len(rows)
    counts = {EXACT: 0, COMPATIBLE: 0, MISSING: 0, INCOMPATIBLE: 0}
    for row in rows:
        counts[row.parity_status] = counts.get(row.parity_status, 0) + 1
    missing_features = [r.feature for r in rows if r.parity_status == MISSING]
    incompatible_features = [r.feature for r in rows if r.parity_status == INCOMPATIBLE]
    return {
        "total_expected_features": total,
        "exact_count": counts[EXACT],
        "compatible_count": counts[COMPATIBLE],
        "missing_count": counts[MISSING],
        "incompatible_count": counts[INCOMPATIBLE],
        "missing_features": missing_features,
        "incompatible_features": incompatible_features,
    }


def hitter_parity_is_sufficient_for_inference(summary: dict) -> bool:
    return summary["incompatible_count"] == 0
