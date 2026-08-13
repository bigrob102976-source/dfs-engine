"""Single source of truth for Pitcher Agent scoring weights, ranges, and
thresholds. Tune the numbers here rather than scattering magic numbers
through the agent code.

Every "range" is a (low, high) pair used to linearly scale a raw stat to
0-100. `invert=True` means a lower raw value produces a higher score
(e.g. ERA, FIP: lower is better for the pitcher).
"""

# --- Model version ------------------------------------------------------------
# One identifier for "which version of the Pitcher Agent produced this
# prediction." Bump this by hand whenever RANGES/COMPONENT_WEIGHTS/
# OVERALL_WEIGHTS/RISK_MODEL/CONFIDENCE_MODEL/PROJECTION_MODEL change in a
# way that would make old predictions not directly comparable to new ones.
# Every prediction snapshot (research/prediction_snapshot.py) records this.
PITCHER_MODEL_VERSION = "0.6.0"

# --- Sub-score input ranges -------------------------------------------------
# Each entry: stat_name -> {"low": ..., "high": ..., "invert": bool}

RANGES = {
    "strikeout": {
        "k_percent": {"low": 12.0, "high": 35.0, "invert": False},
        "k_minus_bb_percent": {"low": 5.0, "high": 25.0, "invert": False},
        "swinging_strike_percent": {"low": 6.0, "high": 16.0, "invert": False},
        "csw_percent": {"low": 24.0, "high": 33.0, "invert": False},
        "opponent_k_percent": {"low": 15.0, "high": 30.0, "invert": False},
        # Milestone 5: a velocity gain over the last 3 starts is itself a
        # strikeout-upside signal (harder stuff -> more swing-and-miss),
        # independent of CSW/SwStr% already capturing the current level.
        # +/-2 mph covers essentially the whole realistic in-season range.
        "velocity_change": {"low": -2.0, "high": 2.0, "invert": False},
    },
    "run_prevention": {
        "siera": {"low": 3.0, "high": 5.5, "invert": True},
        "xfip": {"low": 3.0, "high": 5.5, "invert": True},
        "fip": {"low": 3.0, "high": 5.5, "invert": True},
        "xera": {"low": 2.5, "high": 5.5, "invert": True},
        "xwoba_allowed": {"low": 0.280, "high": 0.360, "invert": True},
        "opponent_woba": {"low": 0.280, "high": 0.360, "invert": True},
        "opponent_iso": {"low": 0.120, "high": 0.220, "invert": True},
        "implied_runs": {"low": 3.0, "high": 5.5, "invert": True},
        # Milestone 5: contact quality allowed is itself a run-prevention
        # signal (weakly hit balls turn into outs more often), not just a
        # "contact_score" signal -- same ranges already used there, reused
        # here under a different composite/weight.
        "hard_hit_percent": {"low": 30.0, "high": 50.0, "invert": True},
        "barrel_percent": {"low": 4.0, "high": 14.0, "invert": True},
        "ground_ball_percent": {"low": 35.0, "high": 55.0, "invert": False},
    },
    "workload": {
        # `recent_innings` assumes the input represents total innings across
        # a recent multi-start sample (e.g. last 3 starts); not a single start.
        "expected_pitch_count": {"low": 70.0, "high": 105.0, "invert": False},
        "recent_pitch_count_average": {"low": 70.0, "high": 105.0, "invert": False},
        "recent_innings": {"low": 9.0, "high": 21.0, "invert": False},
    },
    "contact": {
        "hard_hit_percent": {"low": 30.0, "high": 50.0, "invert": True},
        "barrel_percent": {"low": 4.0, "high": 14.0, "invert": True},
        "ground_ball_percent": {"low": 35.0, "high": 55.0, "invert": False},
    },
    "matchup": {
        "opponent_k_percent": {"low": 15.0, "high": 30.0, "invert": False},
        "opponent_woba": {"low": 0.280, "high": 0.360, "invert": True},
        "opponent_iso": {"low": 0.120, "high": 0.220, "invert": True},
        "implied_runs": {"low": 3.0, "high": 5.5, "invert": True},
    },
    "environment": {
        # Park/weather/umpire factors follow the common convention where
        # 100 = neutral, >100 favors hitters, <100 favors pitchers.
        "park_factor": {"low": 90.0, "high": 110.0, "invert": True},
        "weather_pitching_factor": {"low": 90.0, "high": 110.0, "invert": True},
        "umpire_pitching_factor": {"low": 90.0, "high": 110.0, "invert": True},
    },
    "value": {
        "points_per_1000_salary": {"low": 1.2, "high": 4.0, "invert": False},
    },
}

# --- Weights for combining stats into each composite sub-score -------------
# Weights are renormalized across whichever inputs are actually available.

COMPONENT_WEIGHTS = {
    # Milestone 5: added "velocity_change" (0.10). k_percent/k_minus_bb_percent
    # trimmed slightly (0.35->0.30, 0.25->0.20) so the total still sums to 1.0;
    # swinging_strike_percent/csw_percent/opponent_k_percent weights are
    # unchanged -- they were already here in Milestone 2, just usually empty
    # for real pitchers until this milestone's Statcast enrichment.
    "strikeout": {
        "k_percent": 0.30,
        "k_minus_bb_percent": 0.20,
        "swinging_strike_percent": 0.15,
        "csw_percent": 0.15,
        "opponent_k_percent": 0.10,
        "velocity_change": 0.10,
    },
    # Milestone 5: added hard_hit_percent/barrel_percent/ground_ball_percent
    # (0.08/0.07/0.05) and bumped xera (0.10->0.15) now that we actually
    # collect it. siera/xfip/fip/opponent_woba/opponent_iso trimmed to keep
    # the total at 1.0 -- nothing here is a "hidden" constant, every number
    # is this dict.
    "run_prevention": {
        "siera": 0.18,
        "xfip": 0.14,
        "fip": 0.10,
        "xera": 0.15,
        "xwoba_allowed": 0.15,
        "hard_hit_percent": 0.08,
        "barrel_percent": 0.07,
        "ground_ball_percent": 0.05,
        "opponent_woba": 0.03,
        "opponent_iso": 0.03,
        "implied_runs": 0.02,
    },
    "workload": {
        "expected_pitch_count": 0.5,
        "recent_pitch_count_average": 0.3,
        "recent_innings": 0.2,
    },
    "contact": {
        "hard_hit_percent": 0.45,
        "barrel_percent": 0.35,
        "ground_ball_percent": 0.20,
    },
    "matchup": {
        "opponent_k_percent": 0.35,
        "opponent_woba": 0.30,
        "opponent_iso": 0.15,
        "implied_runs": 0.20,
    },
    "environment": {
        "park_factor": 0.5,
        "weather_pitching_factor": 0.25,
        "umpire_pitching_factor": 0.25,
    },
}

# Environment should nudge, not dominate: compress the raw 0-100 score
# toward the neutral midpoint (50) by this factor before it enters the
# overall score.
ENVIRONMENT_DAMPENING = 0.6

# --- Overall DFS score weighting --------------------------------------------

OVERALL_WEIGHTS = {
    "strikeout_score": 0.30,
    "run_prevention_score": 0.25,
    "matchup_score": 0.15,
    "workload_score": 0.10,
    "contact_score": 0.10,
    "environment_score": 0.05,
    "value_score": 0.05,
}

# --- DraftKings classic pitcher scoring rules -------------------------------
# The single source of truth for DK point values. Both the PREGAME projection
# formula (agents/pitcher_agent.py's _projection, using EXPECTED stats) and
# the POSTGAME actual-scoring formula (evaluation/dk_actual_scoring.py, using
# REAL box score stats) read this same dict -- neither duplicates it.
#
# win/complete_game/complete_game_shutout/no_hitter/hit_batsman are only
# usable postgame (a projection has no meaningful "expected complete game"),
# but they live in this one config anyway per "the exact scoring
# configuration should remain centralized."
#
# NOTE: DraftKings Classic has no "quality start" bonus category -- it is
# not part of the real scoring rules, so no quality_start key is defined
# here. evaluation/dk_actual_scoring.py skips any bonus whose key is absent
# from this dict, so nothing downstream needs an "if quality start exists"
# special case.
DK_SCORING = {
    "innings_pitched": 2.25,
    "strikeout": 2.0,
    "earned_run": -2.0,
    "walk": -0.6,
    "hit_against": -0.6,
    "hit_batsman": -0.6,
    "win": 4.0,
    "complete_game": 2.5,
    "complete_game_shutout": 2.5,  # additional, on top of complete_game
    "no_hitter": 5.0,              # additional, on top of complete_game + complete_game_shutout
}

# --- Baseline projection model ----------------------------------------------
# This is intentionally a simple, documented baseline (see agents/pitcher_agent.py),
# not a sophisticated simulation. Win probability is deliberately excluded:
# we do not have reliable team-level win-probability inputs in this milestone.

PROJECTION_MODEL = {
    "pitches_per_inning": 15.5,
    "batters_per_inning": 4.3,
    # Used only when neither availability.expected_pitch_count nor
    # recent.pitch_count_average is supplied. Heavily flagged via confidence.
    "default_expected_pitch_count": 90.0,
    "min_expected_innings": 2.5,
    "max_expected_innings": 7.5,
    "season_k_weight": 0.7,
    "recent_k_weight": 0.3,
    "season_bb_weight": 0.7,
    "recent_bb_weight": 0.3,
    "league_avg_hard_hit": 35.0,
    "league_avg_barrel": 8.0,
    # Neutral fallbacks used only when a pitcher is missing season K%/BB%
    # entirely; this keeps the baseline formula computable without
    # inventing a pitcher-specific number. Confidence is penalized whenever
    # these fallbacks are used.
    "league_avg_k_percent": 22.0,
    "league_avg_bb_percent": 8.5,
    "baseline_babip": 0.290,
    "contact_multiplier_hard_hit_weight": 0.4,
    "contact_multiplier_barrel_weight": 0.3,
    "contact_multiplier_min": 0.7,
    "contact_multiplier_max": 1.4,
    # Blend whichever run-prevention estimators are supplied (best-first).
    "run_prevention_estimator_weights": {
        "siera": 0.4,
        "xfip": 0.3,
        "fip": 0.2,
        "era": 0.1,
    },
    # Used only when none of siera/xfip/fip/era are supplied at all.
    "default_run_rate": 4.20,
}

CEILING_MODEL = {
    "strikeout_bonus_max": 6.0,
    "workload_bonus_max": 3.0,
    "matchup_bonus_max": 3.0,
}

FLOOR_MODEL = {
    "risk_penalty_max": 14.0,
    "min_floor": 0.0,
}

VALUE_MODEL = {
    "salary_unit": 1000.0,
}

# --- Risk score --------------------------------------------------------------
# Additive penalties on top of a base risk level. Deliberately excludes any
# "bad recent start" result-based signal (recent inputs only carry process
# metrics like K%/BB%/velocity, not recent ERA), per project guidance not to
# overreact to single-start results.

RISK_MODEL = {
    "base_risk": 25.0,
    "low_pitch_count_threshold": 85.0,
    "low_pitch_count_floor": 65.0,
    "low_pitch_count_max_penalty": 15.0,
    "high_bb_percent_threshold": 9.0,
    "high_bb_percent_scale_high": 14.0,
    "high_bb_percent_max_penalty": 15.0,
    "high_barrel_threshold": 9.0,
    "high_barrel_scale_high": 14.0,
    "high_barrel_max_penalty": 12.0,
    "high_implied_runs_threshold": 4.5,
    "high_implied_runs_scale_high": 6.0,
    "high_implied_runs_max_penalty": 12.0,
    "velocity_decline_threshold": -0.8,
    "velocity_decline_scale_high": -2.5,
    "velocity_decline_max_penalty": 12.0,
    "missing_critical_field_penalty": 8.0,
    # Milestone 5: contact-quality and CSW trends. Both use season.hard_hit_percent
    # (absolute level, mirrors the existing barrel penalty above) and
    # trends.csw_trend (recent-vs-season delta) respectively.
    "high_hard_hit_threshold": 42.0,
    "high_hard_hit_scale_high": 50.0,
    "high_hard_hit_max_penalty": 10.0,
    "csw_decline_threshold": -1.0,
    "csw_decline_scale_high": -5.0,
    "csw_decline_max_penalty": 10.0,
}

# --- Confidence score --------------------------------------------------------

CONFIDENCE_MODEL = {
    "base_confidence": 100.0,
    "critical_missing_penalty": 12.0,
    "minor_missing_penalty": 4.0,
    "min_confidence": 5.0,
    # Milestone 5: confidence must reflect SAMPLE SIZE, not just field
    # presence -- a pitcher with 8 innings this season and a 1-start
    # "recent" window has real numbers in every field, but they're much
    # less trustworthy than a full-workload starter's. Same 0-penalty
    # -at-threshold / ramping-to-max-at-floor shape as the risk penalties.
    "season_sample_innings_threshold": 40.0,
    "season_sample_innings_floor": 10.0,
    "season_sample_max_penalty": 10.0,
    # Innings (not start count) so this works whichever source populated
    # recent.innings -- MLB Stats game-log recent form or Statcast recent
    # form both set it the same way. ~15 innings is a normal healthy
    # 3-start sample; well under that means a shortened/partial window.
    "recent_sample_innings_threshold": 15.0,
    "recent_sample_innings_floor": 5.0,
    "recent_sample_max_penalty": 6.0,
}

# --- Tagging thresholds -------------------------------------------------------

TAG_THRESHOLDS = {
    "elite_k_upside_score": 85.0,
    "strong_k_matchup_opponent_k_percent": 25.0,
    "low_walk_rate_bb_percent": 6.0,
    "good_run_environment_implied_runs": 3.8,
    "good_run_environment_score": 70.0,
    "high_pitch_count": 100.0,
    "salary_value_score": 80.0,
    "velocity_up": 0.6,
    "velocity_down": -1.0,
    "dangerous_opponent_woba": 0.340,
    "dangerous_opponent_implied_runs": 5.0,
    "high_barrel_risk": 10.0,
    "walk_risk_bb_percent": 10.0,
    "limited_workload_pitch_count": 80.0,
    "ace_profile_strikeout_score": 80.0,
    "ace_profile_run_prevention_score": 80.0,
    "ace_profile_workload_score": 65.0,
    # Milestone 5: Statcast-driven tags. Thresholds reuse the same scale
    # conventions as the RANGES above (e.g. csw_percent's 24-33 range ->
    # "elite" sits near the top of it).
    "elite_csw_percent": 30.0,
    "elite_swinging_strike_percent": 14.0,
    "contact_suppression_hard_hit_max": 33.0,
    "contact_suppression_barrel_max": 5.0,
    "ground_ball_specialist_percent": 50.0,
    "xera_regression_gap": 0.60,  # |ERA - xERA| gap that counts as a meaningful regression signal
}

# --- Trend-tag agreement -------------------------------------------------------
# "positive_trend"/"negative_trend" summarize trends.* into one tag: count how
# many of the (up to 5) directional signals below point the same way among
# whichever are actually available, and require at least this many in
# agreement (and at least this many total available) before tagging either
# direction. Keeps a single missing/flat metric from flipping the tag.
TREND_MODEL = {
    "signal_threshold": 0.3,  # a trend must move at least this much to count as "positive" or "negative" at all
    "min_signals_available": 3,
    "min_signals_agreeing": 3,
}

# --- Slate-relative context -----------------------------------------------------
# Used only by analyze_slate (never a single-pitcher analyze_pitcher call) to
# add one extra reason for pitchers whose CSW% stands out on THIS slate, e.g.
# "31.2% CSW ranks 2nd of 30 on today's slate." Requires a minimum slate size
# so a 2-pitcher test fixture doesn't trivially call both of them "top".
SLATE_CONTEXT = {
    "min_slate_size_for_ranking": 5,
    "top_rank_cutoff": 3,  # top N by season CSW% get the bonus reason
}
