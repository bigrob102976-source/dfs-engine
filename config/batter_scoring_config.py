"""Single source of truth for Batter Agent scoring weights, ranges, and
thresholds. Mirrors config/scoring_config.py's structure exactly (same
RANGES/COMPONENT_WEIGHTS/renormalization semantics) but is a completely
separate file/dict namespace -- the Batter Agent never reads
config.scoring_config, and the Pitcher Agent never reads this file.

Every "range" is a (low, high) pair used to linearly scale a raw stat to
0-100. `invert=True` means a lower raw value produces a higher score.
"""

# --- Model version ------------------------------------------------------------
BATTER_MODEL_VERSION = "0.1.0"

# --- Sub-score input ranges -------------------------------------------------

RANGES = {
    "hitting_skill": {
        "xwoba": {"low": 0.280, "high": 0.400, "invert": False},
        "woba": {"low": 0.280, "high": 0.400, "invert": False},
        "xslg": {"low": 0.350, "high": 0.550, "invert": False},
        "iso": {"low": 0.100, "high": 0.280, "invert": False},
        "barrel_percent": {"low": 4.0, "high": 16.0, "invert": False},
        "hard_hit_percent": {"low": 30.0, "high": 50.0, "invert": False},
        "exit_velocity": {"low": 85.0, "high": 95.0, "invert": False},
    },
    "power": {
        "iso": {"low": 0.100, "high": 0.280, "invert": False},
        "xslg": {"low": 0.350, "high": 0.550, "invert": False},
        "barrel_percent": {"low": 4.0, "high": 16.0, "invert": False},
        "hard_hit_percent": {"low": 30.0, "high": 50.0, "invert": False},
        "exit_velocity": {"low": 85.0, "high": 95.0, "invert": False},
    },
    "contact": {
        # Lower K% is better for a hitter -> invert. BB%/xBA: higher is better.
        "k_percent": {"low": 12.0, "high": 32.0, "invert": True},
        "bb_percent": {"low": 4.0, "high": 15.0, "invert": False},
        "xba": {"low": 0.220, "high": 0.300, "invert": False},
    },
    "matchup": {
        # Higher opposing-pitcher K% makes the matchup HARDER for the hitter -> invert.
        "pitcher_k_percent": {"low": 12.0, "high": 35.0, "invert": True},
        # Higher xwOBA/hard-hit ALLOWED by the pitcher makes the matchup EASIER -> not inverted.
        "pitcher_xwoba_allowed": {"low": 0.280, "high": 0.360, "invert": False},
        "pitcher_hard_hit_allowed": {"low": 30.0, "high": 50.0, "invert": False},
        # The hitter's own platoon wOBA vs this pitcher's throwing hand.
        "platoon_woba": {"low": 0.280, "high": 0.400, "invert": False},
    },
    "recent_trend": {
        # Trend fields are already signed so "higher = more favorable for
        # the hitter" (see models.batter.TrendMetrics) -- none of these invert.
        "exit_velocity_trend": {"low": -3.0, "high": 3.0, "invert": False},
        "hard_hit_trend": {"low": -10.0, "high": 10.0, "invert": False},
        "barrel_trend": {"low": -5.0, "high": 5.0, "invert": False},
        "xwoba_trend": {"low": -0.05, "high": 0.05, "invert": False},
        "strikeout_rate_trend": {"low": -8.0, "high": 8.0, "invert": False},
    },
    "lineup_position": {
        # Lower batting-order number = more plate-appearance opportunity -> invert.
        "batting_order": {"low": 1.0, "high": 9.0, "invert": True},
    },
    "value": {
        "points_per_1000_salary": {"low": 1.5, "high": 5.0, "invert": False},
    },
}

# --- Weights for combining stats into each composite sub-score -------------
# Weights are renormalized across whichever inputs are actually available,
# exactly like config.scoring_config.COMPONENT_WEIGHTS.

COMPONENT_WEIGHTS = {
    "hitting_skill": {
        "xwoba": 0.25, "woba": 0.20, "xslg": 0.15, "iso": 0.15,
        "barrel_percent": 0.10, "hard_hit_percent": 0.10, "exit_velocity": 0.05,
    },
    "power": {
        "iso": 0.30, "xslg": 0.25, "barrel_percent": 0.20,
        "hard_hit_percent": 0.15, "exit_velocity": 0.10,
    },
    "contact": {
        "k_percent": 0.45, "bb_percent": 0.30, "xba": 0.25,
    },
    "matchup": {
        "pitcher_k_percent": 0.30, "pitcher_xwoba_allowed": 0.25,
        "pitcher_hard_hit_allowed": 0.20, "platoon_woba": 0.25,
    },
    "recent_trend": {
        "exit_velocity_trend": 0.20, "hard_hit_trend": 0.20, "barrel_trend": 0.15,
        "xwoba_trend": 0.25, "strikeout_rate_trend": 0.20,
    },
    "lineup_position": {
        "batting_order": 1.0,
    },
}

# --- Overall DFS score weighting --------------------------------------------

OVERALL_WEIGHTS = {
    "hitting_skill_score": 0.25,
    "power_score": 0.20,
    "matchup_score": 0.15,
    "contact_score": 0.10,
    "recent_trend_score": 0.10,
    "lineup_position_score": 0.10,
    "environment_score": 0.05,
    "value_score": 0.05,
}

# --- DraftKings classic hitter scoring rules ---------------------------------
# Centralized so the (future) actual-scoring path can reuse it exactly like
# evaluation/dk_actual_scoring.py reuses config.scoring_config.DK_SCORING.
# No "hit for the cycle" bonus -- rare enough that modeling it isn't worth
# the complexity for a research-mode baseline.
DK_HITTER_SCORING = {
    "single": 3.0,
    "double": 5.0,
    "triple": 8.0,
    "home_run": 10.0,
    "rbi": 2.0,
    "run": 2.0,
    "walk": 2.0,
    "hit_by_pitch": 2.0,
    "stolen_base": 5.0,
}

# --- Baseline projection model ----------------------------------------------
# Intentionally simple (see agents/batter_agent.py's `_projection`): expected
# PA from batting order, expected BB from BB%, expected hits from AVG, hit
# TYPE distribution from the hitter's own real season hit-type ratios.
# Deliberately excludes Runs/RBI (no team-context/lineup-protection model
# exists yet) rather than inventing a run environment.

PROJECTION_MODEL = {
    # Expected plate appearances by batting order slot -- a workload
    # assumption (same spirit as the Pitcher Agent's default pitch count),
    # not a statistic. Decreasing down the order matches how MLB lineups
    # are actually constructed.
    "expected_pa_by_order": {
        1: 4.6, 2: 4.5, 3: 4.4, 4: 4.3, 5: 4.2, 6: 4.0, 7: 3.9, 8: 3.8, 9: 3.7,
    },
    "default_expected_pa": 4.0,  # used only if batting_order is somehow missing
    # Season/recent blend weights for K%/BB% (same 0.7/0.3 split the
    # Pitcher Agent uses for its own blended rates).
    "season_k_weight": 0.7,
    "recent_k_weight": 0.3,
    "season_bb_weight": 0.7,
    "recent_bb_weight": 0.3,
    # Neutral fallbacks, used only when a hitter's OWN season rate is missing
    # entirely -- keeps the formula computable without inventing a
    # player-specific number; confidence is penalized whenever used.
    "league_avg_k_percent": 22.0,
    "league_avg_bb_percent": 8.5,
    "league_avg_avg": 0.245,
    "league_avg_double_share_of_hits": 0.20,
    "league_avg_triple_share_of_hits": 0.02,
    "league_avg_hr_share_of_hits": 0.13,
    "league_avg_sb_per_pa": 0.012,
}

CEILING_MODEL = {
    "power_bonus_max": 5.0,
    "matchup_bonus_max": 3.0,
    "lineup_position_bonus_max": 2.0,
}

FLOOR_MODEL = {
    "risk_penalty_max": 10.0,
    "min_floor": 0.0,
}

VALUE_MODEL = {
    "salary_unit": 1000.0,
}

# --- Risk score --------------------------------------------------------------

RISK_MODEL = {
    "base_risk": 25.0,
    "high_k_percent_threshold": 24.0,
    "high_k_percent_scale_high": 34.0,
    "high_k_percent_max_penalty": 15.0,
    "poor_lineup_slot_threshold": 6.0,
    "poor_lineup_slot_scale_high": 9.0,
    "poor_lineup_slot_max_penalty": 10.0,
    "small_sample_pa_threshold": 150.0,
    "small_sample_pa_floor": 30.0,
    "small_sample_max_penalty": 15.0,
    "weak_matchup_threshold": 50.0,
    "weak_matchup_scale_low": 20.0,
    "weak_matchup_max_penalty": 10.0,
    # "Volatile power-only profile": elevated ISO combined with elevated K%
    # (all-or-nothing power hitter) adds a flat penalty on top of the
    # continuous K%-based penalty above.
    "volatile_power_iso_threshold": 0.220,
    "volatile_power_k_percent_threshold": 27.0,
    "volatile_power_flat_penalty": 8.0,
    "missing_critical_field_penalty": 8.0,
}

# --- Confidence score --------------------------------------------------------
# Missing salary is deliberately NOT part of either checklist below --
# salary isn't collected yet at all, and the milestone is explicit that
# this must not meaningfully reduce confidence.

CONFIDENCE_MODEL = {
    "base_confidence": 100.0,
    "critical_missing_penalty": 12.0,
    "minor_missing_penalty": 4.0,
    "min_confidence": 5.0,
    "season_sample_pa_threshold": 200.0,
    "season_sample_pa_floor": 40.0,
    "season_sample_max_penalty": 12.0,
    "recent_sample_pa_threshold": 30.0,
    "recent_sample_pa_floor": 8.0,
    "recent_sample_max_penalty": 6.0,
}

# --- Tagging thresholds -------------------------------------------------------

TAG_THRESHOLDS = {
    "elite_power_iso": 0.230,
    "elite_barrel_percent": 12.0,
    "elite_hard_hit_percent": 45.0,
    "elite_xwoba": 0.370,
    "low_strikeout_k_percent": 16.0,
    "walk_upside_bb_percent": 12.0,
    "leadoff_order": 1,
    "top_order_max": 3,
    "cleanup_order": 4,
    "bottom_order_min": 7,
    "hot_statcast_score": 70.0,   # recent_trend_score at/above this -> hot_statcast
    "cold_statcast_score": 30.0,  # recent_trend_score at/below this -> cold_statcast
    "power_sleeper_recent_hard_hit": 42.0,
    "power_sleeper_season_iso_max": 0.170,
    "high_k_risk_k_percent": 27.0,
    "tough_pitcher_matchup_score": 35.0,
    "strong_pitcher_matchup_score": 65.0,
}

# --- Trend-tag agreement -------------------------------------------------------
# Same pattern as config.scoring_config.TREND_MODEL: how many of the
# (up to 5) directional trend signals must agree before tagging
# positive_contact_trend / negative_contact_trend.
TREND_MODEL = {
    "signal_threshold": 0.3,
    "min_signals_available": 3,
    "min_signals_agreeing": 3,
}
