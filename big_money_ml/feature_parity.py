"""Milestone 32.2B -- training/live feature parity audit.

For every one of the 117 features historical_models.pitcher_v1 was
trained on, this module reports whether -- and how -- that SAME feature
definition can be computed from data available before today's games
start. Nothing here redefines a feature; every "EXACT"/"COMPATIBLE" row
below is produced by calling the literal training-time function
(historical_mlb.rolling.*, historical_mlb.statcast_aggregation.*) with
live-fetched inputs instead of warehouse inputs -- see live_features.py.

Statuses:
    EXACT        -- identical function, identical live data shape, same window.
    COMPATIBLE   -- same feature definition, but the live data source needed a
                    different endpoint/adapter than the historical one (e.g.
                    a forecast vs. archive weather call) -- not applicable in
                    V1 (weather is MISSING, see below), reserved for future use.
    MISSING      -- the live pipeline has no source for this feature yet;
                    passed through as None/NaN. Only ever used where the
                    frozen model was explicitly trained to tolerate missing
                    values (HistGradientBoostingRegressor's native NaN
                    handling) -- never fabricated.
    INCOMPATIBLE -- a live source exists but means something structurally
                    different from the training-time definition; must never
                    be silently substituted.
"""

from dataclasses import dataclass
from typing import List

from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS, _family_of

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


# One entry per FAMILY (historical_models.pitcher_v1.features._family_of),
# describing the common definition/sources/status shared by every column in
# that family. A handful of families need a column-level override below
# because not every column in the family is sourced identically.
_FAMILY_PARITY = {
    "rolling": FeatureParityRow(
        feature="rolling_*", training_definition="Trailing 7d/14d/30d/season-to-date pitching totals from MLB Stats API gameLog entries, aggregated by historical_mlb.rolling.build_rolling_pitcher_stats.",
        historical_source="historical_mlb.sources.mlb_stats.fetch_cached_season_game_log (re-exports research.collector.fetch_pitcher_game_log verbatim)",
        live_source="Same function (historical_mlb.sources.mlb_stats.fetch_cached_season_game_log), called for the CURRENT season instead of a historical one.",
        live_availability="Available for any pitcher with at least one current-season MLB appearance; empty (not fabricated) for a player with zero starts this season.",
        transformation="None -- historical_mlb.rolling.build_rolling_pitcher_stats is called directly, unmodified.",
        parity_status=EXACT,
    ),
    "workload": FeatureParityRow(
        feature="days_rest / previous_start_pitch_count / starts_last_30d / innings_last_30d",
        training_definition="Derived from the same season_game_log via historical_mlb.pitcher_features._previous_start and historical_mlb.rolling.build_rolling_pitcher_stats(window_days=30).",
        historical_source="Same game log as rolling_*.",
        live_source="Same game log as rolling_* (live).",
        live_availability="Available whenever the pitcher has at least one prior start this season; days_rest/previous_start_pitch_count are None for a pitcher's first start of the season (same as training).",
        transformation="None -- the private helper is imported and called directly, not reimplemented.",
        parity_status=EXACT,
    ),
    "statcast": FeatureParityRow(
        feature="statcast_*_14d / statcast_*_30d / statcast_*_season",
        training_definition="Trailing 14d/30d/30d-buffer-capped-\"season\" Statcast pitch-level aggregates (hard-hit%, barrel-rate proxy, xwOBA, xSLG, exit velocity, launch angle) via historical_mlb.rolling.aggregate_statcast_rates. NOTE: the training warehouse's own STATCAST_BUFFER_DAYS=30 means \"_season\" here is ALSO only a trailing-30-day proxy, not a true full-season aggregate -- documented in M32.1's own statcast_aggregation.py docstring.",
        historical_source="historical_mlb.warehouse_builder.StatcastBuffer, fed by historical_mlb.sources.statcast.fetch_cached_statcast_csv_text (Baseball Savant CSV search).",
        live_source="The SAME historical_mlb.warehouse_builder.StatcastBuffer class and historical_mlb.sources.statcast.fetch_cached_statcast_csv_text function, advanced through the 30 real calendar days immediately preceding today.",
        live_availability="Available for any pitcher who appeared in at least one game in the trailing 30 days; empty (not fabricated) otherwise -- identical behavior to a rookie/injury-return case in training.",
        transformation="None -- StatcastBuffer and aggregate_statcast_rates are reused unmodified.",
        parity_status=EXACT,
    ),
    "platoon": FeatureParityRow(
        feature="platoon_vs_lhb_* / platoon_vs_rhb_*",
        training_definition="historical_mlb.statcast_aggregation.pitcher_platoon_splits_allowed over the same Statcast window buffer.",
        historical_source="Same StatcastBuffer as statcast_*.",
        live_source="Same StatcastBuffer as statcast_* (live).",
        live_availability="Available whenever the pitcher faced at least one batter of that stand in the trailing 30 days.",
        transformation="None.",
        parity_status=EXACT,
    ),
    "opponent": FeatureParityRow(
        feature="opponent_k_pct_season / opponent_bb_pct_season / opponent_hr_rate_season / opponent_woba_season / opponent_sample_games",
        training_definition="historical_mlb.statcast_aggregation.opponent_offense_aggregate over the same 30-day Statcast buffer, filtered to the opposing team's plate appearances.",
        historical_source="Same StatcastBuffer as statcast_*.",
        live_source="Same StatcastBuffer as statcast_* (live), filtered to today's opponent team abbreviation.",
        live_availability="Available whenever the opponent team played at least one game in the trailing 30 days (true for every team on a normal schedule).",
        transformation="None.",
        parity_status=EXACT,
    ),
    "weather": FeatureParityRow(
        feature="weather_available / weather_temperature_f / weather_wind_speed_mph / weather_wind_direction_deg / weather_precipitation / weather_humidity_pct",
        training_definition="Open-Meteo HISTORICAL ARCHIVE (archive-api.open-meteo.com) hourly weather at the home team's approximate coordinates, via historical_mlb.sources.weather.",
        historical_source="historical_mlb.sources.weather.fetch_cached_weather_json (archive endpoint) -- 0% missing across all 9,714 training rows.",
        live_source="NOT IMPLEMENTED in M32.2B. The archive endpoint has no data for a game that hasn't been played yet; a live forecast fetch was deliberately out of scope for this milestone.",
        live_availability="Never available live in V1 -- weather_available is always False, every weather_* column is always None/NaN.",
        transformation="No live weather fetch performed. Passed through as missing.",
        parity_status=MISSING,
    ),
    "venue": FeatureParityRow(
        feature="team / venue_id / home_away",
        training_definition="Identity fields carried straight through from the game/lineup join -- not statistics.",
        historical_source="historical_mlb.game_universe / crosswalk join.",
        live_source="research_output/<date>/games.json (home_team_abbr/away_team_abbr/venue_id) + the eligible pitcher's own team from the DK player pool's M30.1 eligibility join.",
        live_availability="Always available for any pitcher the eligibility layer already resolved to a game.",
        transformation="None -- identity passthrough.",
        parity_status=EXACT,
    ),
    "core": FeatureParityRow(
        feature="opponent",
        training_definition="Opponent team abbreviation, carried straight through from the game/lineup join -- not a statistic. (Note: historical_mlb.manifest's own family classifier groups this single identity column under \"core\" rather than \"venue\" -- a naming quirk in the manifest, not a live-parity issue.)",
        historical_source="historical_mlb.game_universe / crosswalk join.",
        live_source="research_output/<date>/games.json (home_team_abbr/away_team_abbr) + the eligible pitcher's own opponent from the DK player pool's M30.1 eligibility join.",
        live_availability="Always available for any pitcher the eligibility layer already resolved to a game.",
        transformation="None -- identity passthrough.",
        parity_status=EXACT,
    ),
    "handedness": FeatureParityRow(
        feature="throw_hand / bat_hand",
        training_definition="historical_mlb.sources.mlb_stats.person_handedness(fetch_person(player_id)) -- MLB Stats API /people/{id}.",
        historical_source="research.collector.fetch_person, re-exported verbatim by historical_mlb.sources.mlb_stats.",
        live_source="The SAME research.collector.fetch_person + historical_mlb.sources.mlb_stats.person_handedness functions, called live.",
        live_availability="Available for any player MLB Stats API has bio data for (effectively all active MLB pitchers).",
        transformation="None.",
        parity_status=EXACT,
    ),
}


# historical_mlb.manifest's own family classifier groups venue_roof_type
# under "weather" (same startswith check as weather_*), but it is NOT
# weather -- it's a static per-team roof lookup, always available live.
# Column-level override so it doesn't inherit the "weather" family's
# MISSING status.
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


def build_feature_parity_report() -> List[FeatureParityRow]:
    """One row per FEATURE_COLUMNS entry (117 rows), each stamped with
    its exact column name (not just the family template)."""
    rows: List[FeatureParityRow] = []
    for column in FEATURE_COLUMNS:
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


def summarize_parity(rows: List[FeatureParityRow]) -> dict:
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


def parity_is_sufficient_for_inference(summary: dict) -> bool:
    """Live inference must STOP if any feature is INCOMPATIBLE (a
    silently-wrong substitution risk). A MISSING feature is only
    acceptable because the frozen model (HistGradientBoostingRegressor)
    was explicitly trained with native NaN handling -- verified by
    historical_models.pitcher_v1's own model-selection tests."""
    return summary["incompatible_count"] == 0
