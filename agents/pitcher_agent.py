"""Pitcher Agent: deterministic scoring for starting pitchers.

Pipeline (per CLAUDE.md):

    data source -> normalization -> pitcher features -> Pitcher Agent scoring -> ranked board

This module is the last two stages. It never calls an external API or an
LLM: every number here is produced by transparent, testable Python logic
from the fields on `PitcherInput`. Missing non-critical stats are
tolerated (the affected sub-score renormalizes over whatever is present);
missing critical stats lower confidence and raise risk. Nothing is ever
invented to fill a gap.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import scoring_config as cfg
from models.pitcher import PitcherBoardEntry, PitcherInput

# ----------------------------------------------------------------------------
# Small numeric helpers
# ----------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _scale(value: Optional[float], low: float, high: float, invert: bool = False) -> Optional[float]:
    """Linearly scale `value` from [low, high] to [0, 100], clamped."""
    if value is None:
        return None
    if high == low:
        return 50.0
    pct = (value - low) / (high - low)
    pct = _clamp(pct, 0.0, 1.0)
    if invert:
        pct = 1.0 - pct
    return pct * 100.0


def _linear_penalty(value: Optional[float], start: float, extreme: float, max_penalty: float) -> float:
    """0 penalty at `start`, ramping linearly to `max_penalty` at `extreme`.

    Works whether the risky direction is up (extreme > start) or down
    (extreme < start).
    """
    if value is None:
        return 0.0
    span = extreme - start
    if span == 0:
        return 0.0
    pct = (value - start) / span
    pct = _clamp(pct, 0.0, 1.0)
    return pct * max_penalty


def _composite_score(purpose: str, raw_values: Dict[str, Optional[float]]) -> Tuple[float, List[str]]:
    """Weighted-average a set of stats onto 0-100, renormalizing over
    whichever inputs are actually present.

    Returns (score, missing_stat_names). When every input for this
    composite is missing, returns a neutral 50.0 rather than crashing or
    guessing — the caller's confidence/risk accounting is responsible for
    reflecting that gap.
    """
    ranges = cfg.RANGES[purpose]
    weights = cfg.COMPONENT_WEIGHTS[purpose]
    total = 0.0
    total_weight = 0.0
    missing = []
    for stat_name, weight in weights.items():
        value = raw_values.get(stat_name)
        if value is None:
            missing.append(stat_name)
            continue
        r = ranges[stat_name]
        scaled = _scale(value, r["low"], r["high"], r["invert"])
        total += scaled * weight
        total_weight += weight
    if total_weight == 0:
        return 50.0, missing
    return total / total_weight, missing


def _blend(a: Optional[float], b: Optional[float], weight_a: float, weight_b: float) -> Optional[float]:
    """Weighted blend of two optional values, falling back to whichever is present."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a * weight_a + b * weight_b


# ----------------------------------------------------------------------------
# Derived features
# ----------------------------------------------------------------------------


@dataclass
class DerivedFeatures:
    blended_k_percent: Optional[float]
    blended_bb_percent: Optional[float]
    velocity_change: Optional[float]
    expected_pitch_count: float
    workload_source_present: bool
    workload_source_label: str
    expected_innings: float
    batters_faced: float
    run_rate_estimate: float
    run_rate_estimator_present: bool
    run_rate_estimator_label: str
    contact_multiplier: float
    expected_k: float
    expected_bb: float
    expected_hits: float
    expected_earned_runs: float


def _derive_features(p: PitcherInput) -> DerivedFeatures:
    pm = cfg.PROJECTION_MODEL

    blended_k_percent = _blend(p.season.k_percent, p.recent.k_percent, pm["season_k_weight"], pm["recent_k_weight"])
    blended_bb_percent = _blend(p.season.bb_percent, p.recent.bb_percent, pm["season_bb_weight"], pm["recent_bb_weight"])

    velocity_change = None
    if p.recent.velocity is not None and p.recent.season_velocity is not None:
        velocity_change = p.recent.velocity - p.recent.season_velocity

    if p.availability.expected_pitch_count is not None:
        expected_pitch_count = p.availability.expected_pitch_count
        workload_source_present = True
        workload_source_label = "confirmed expected pitch count"
    elif p.recent.pitch_count_average is not None:
        expected_pitch_count = p.recent.pitch_count_average
        workload_source_present = True
        workload_source_label = "recent average pitch count"
    else:
        expected_pitch_count = pm["default_expected_pitch_count"]
        workload_source_present = False
        workload_source_label = "league-average default (no pitch-count data supplied)"

    expected_innings = _clamp(
        expected_pitch_count / pm["pitches_per_inning"],
        pm["min_expected_innings"],
        pm["max_expected_innings"],
    )
    batters_faced = expected_innings * pm["batters_per_inning"]

    run_rate_total = 0.0
    run_rate_weight = 0.0
    used_estimators = []
    for stat_name, weight in pm["run_prevention_estimator_weights"].items():
        value = getattr(p.season, stat_name, None)
        if value is None:
            continue
        run_rate_total += value * weight
        run_rate_weight += weight
        used_estimators.append(stat_name)
    if run_rate_weight > 0:
        run_rate_estimate = run_rate_total / run_rate_weight
        run_rate_estimator_present = True
        run_rate_estimator_label = "+".join(used_estimators)
    else:
        run_rate_estimate = pm["default_run_rate"]
        run_rate_estimator_present = False
        run_rate_estimator_label = "league-average default (no SIERA/xFIP/FIP/ERA supplied)"

    hard_hit_component = 0.0
    if p.season.hard_hit_percent is not None:
        hard_hit_component = (p.season.hard_hit_percent - pm["league_avg_hard_hit"]) / pm["league_avg_hard_hit"]
    barrel_component = 0.0
    if p.season.barrel_percent is not None:
        barrel_component = (p.season.barrel_percent - pm["league_avg_barrel"]) / pm["league_avg_barrel"]
    contact_multiplier = 1.0 + hard_hit_component * pm["contact_multiplier_hard_hit_weight"] + barrel_component * pm["contact_multiplier_barrel_weight"]
    contact_multiplier = _clamp(contact_multiplier, pm["contact_multiplier_min"], pm["contact_multiplier_max"])

    k_rate = (blended_k_percent if blended_k_percent is not None else pm["league_avg_k_percent"]) / 100.0
    bb_rate = (blended_bb_percent if blended_bb_percent is not None else pm["league_avg_bb_percent"]) / 100.0
    expected_k = batters_faced * k_rate
    expected_bb = batters_faced * bb_rate
    balls_in_play = max(batters_faced - expected_k - expected_bb, 0.0)
    expected_hits = balls_in_play * pm["baseline_babip"] * contact_multiplier
    expected_earned_runs = run_rate_estimate * (expected_innings / 9.0)

    return DerivedFeatures(
        blended_k_percent=blended_k_percent,
        blended_bb_percent=blended_bb_percent,
        velocity_change=velocity_change,
        expected_pitch_count=expected_pitch_count,
        workload_source_present=workload_source_present,
        workload_source_label=workload_source_label,
        expected_innings=expected_innings,
        batters_faced=batters_faced,
        run_rate_estimate=run_rate_estimate,
        run_rate_estimator_present=run_rate_estimator_present,
        run_rate_estimator_label=run_rate_estimator_label,
        contact_multiplier=contact_multiplier,
        expected_k=expected_k,
        expected_bb=expected_bb,
        expected_hits=expected_hits,
        expected_earned_runs=expected_earned_runs,
    )


# ----------------------------------------------------------------------------
# Missing-data accounting (drives risk + confidence)
# ----------------------------------------------------------------------------


def _missing_data(p: PitcherInput, features: DerivedFeatures) -> Tuple[List[str], List[str]]:
    critical_checks = [
        ("season_k_percent", p.season.k_percent is not None),
        ("season_bb_percent", p.season.bb_percent is not None),
        ("run_prevention_estimator", features.run_rate_estimator_present),
        ("workload_source", features.workload_source_present),
        ("opponent_implied_runs", p.opponent_stats.implied_runs is not None),
    ]
    minor_checks = [
        ("k_minus_bb_percent", p.season.k_minus_bb_percent is not None),
        ("swinging_strike_percent", p.season.swinging_strike_percent is not None),
        # CSW is only obtainable at the RECENT (last-3-starts) grain this
        # milestone -- season CSW has no lightweight source (see
        # research/statcast_enrichment.py's module docstring), so checking
        # for it would permanently and unfairly flag every pitcher.
        ("csw_percent", p.recent.csw_percent is not None),
        ("xera", p.season.xera is not None),
        ("xwoba_allowed", p.season.xwoba_allowed is not None),
        ("xba", p.season.xba is not None),
        ("hard_hit_percent", p.season.hard_hit_percent is not None),
        ("barrel_percent", p.season.barrel_percent is not None),
        ("ground_ball_percent", p.season.ground_ball_percent is not None),
        ("avg_exit_velocity_allowed", p.season.avg_exit_velocity_allowed is not None),
        ("opponent_strikeout_percent", _opponent_k_percent(p) is not None),
        ("opponent_woba_vs_hand", p.opponent_stats.woba_vs_hand is not None),
        ("opponent_iso_vs_hand", p.opponent_stats.iso_vs_hand is not None),
        ("velocity_data", features.velocity_change is not None),
        ("recent_innings", p.recent.innings is not None),
        ("park_factor", p.game.park_factor is not None),
        ("weather_pitching_factor", p.game.weather_pitching_factor is not None),
        ("umpire_pitching_factor", p.game.umpire_pitching_factor is not None),
        ("throwing_hand", p.throwing_hand is not None),
    ]
    critical_missing = [name for name, present in critical_checks if not present]
    minor_missing = [name for name, present in minor_checks if not present]
    return critical_missing, minor_missing


# ----------------------------------------------------------------------------
# Sub-scores
# ----------------------------------------------------------------------------


def _sub_scores(p: PitcherInput, features: DerivedFeatures) -> Dict[str, float]:
    opponent_k_percent = _opponent_k_percent(p)

    strikeout_score, _ = _composite_score("strikeout", {
        "k_percent": p.season.k_percent,
        "k_minus_bb_percent": p.season.k_minus_bb_percent,
        "swinging_strike_percent": p.season.swinging_strike_percent,
        "csw_percent": p.season.csw_percent,
        "opponent_k_percent": opponent_k_percent,
        # Milestone 5: velocity gain over the last 3 starts feeds strikeout
        # upside directly (see config.RANGES["strikeout"]["velocity_change"]).
        "velocity_change": features.velocity_change,
    })

    run_prevention_score, _ = _composite_score("run_prevention", {
        "siera": p.season.siera,
        "xfip": p.season.xfip,
        "fip": p.season.fip,
        "xera": p.season.xera,
        "xwoba_allowed": p.season.xwoba_allowed,
        "opponent_woba": p.opponent_stats.woba_vs_hand,
        "opponent_iso": p.opponent_stats.iso_vs_hand,
        "implied_runs": p.opponent_stats.implied_runs,
        # Milestone 5: contact quality allowed also informs run prevention
        # (see config.COMPONENT_WEIGHTS["run_prevention"] for the added weights).
        "hard_hit_percent": p.season.hard_hit_percent,
        "barrel_percent": p.season.barrel_percent,
        "ground_ball_percent": p.season.ground_ball_percent,
    })

    workload_score, _ = _composite_score("workload", {
        "expected_pitch_count": p.availability.expected_pitch_count,
        "recent_pitch_count_average": p.recent.pitch_count_average,
        "recent_innings": p.recent.innings,
    })

    contact_score, _ = _composite_score("contact", {
        "hard_hit_percent": p.season.hard_hit_percent,
        "barrel_percent": p.season.barrel_percent,
        "ground_ball_percent": p.season.ground_ball_percent,
    })

    matchup_score, _ = _composite_score("matchup", {
        "opponent_k_percent": opponent_k_percent,
        "opponent_woba": p.opponent_stats.woba_vs_hand,
        "opponent_iso": p.opponent_stats.iso_vs_hand,
        "implied_runs": p.opponent_stats.implied_runs,
    })

    environment_raw, _ = _composite_score("environment", {
        "park_factor": p.game.park_factor,
        "weather_pitching_factor": p.game.weather_pitching_factor,
        "umpire_pitching_factor": p.game.umpire_pitching_factor,
    })
    environment_score = 50.0 + (environment_raw - 50.0) * cfg.ENVIRONMENT_DAMPENING

    return {
        "strikeout_score": strikeout_score,
        "run_prevention_score": run_prevention_score,
        "workload_score": workload_score,
        "contact_score": contact_score,
        "matchup_score": matchup_score,
        "environment_score": environment_score,
    }


# ----------------------------------------------------------------------------
# Projection / ceiling / floor / value
# ----------------------------------------------------------------------------


def _projection(features: DerivedFeatures) -> float:
    dk = cfg.DK_SCORING
    points = (
        features.expected_innings * dk["innings_pitched"]
        + features.expected_k * dk["strikeout"]
        + features.expected_earned_runs * dk["earned_run"]
        + features.expected_bb * dk["walk"]
        + features.expected_hits * dk["hit_against"]
    )
    return max(points, 0.0)


def _ceiling(projection: float, scores: Dict[str, float]) -> float:
    cm = cfg.CEILING_MODEL
    return projection + (
        (scores["strikeout_score"] / 100.0) * cm["strikeout_bonus_max"]
        + (scores["workload_score"] / 100.0) * cm["workload_bonus_max"]
        + (scores["matchup_score"] / 100.0) * cm["matchup_bonus_max"]
    )


def _floor(projection: float, risk_score: float) -> float:
    fm = cfg.FLOOR_MODEL
    return max(projection - (risk_score / 100.0) * fm["risk_penalty_max"], fm["min_floor"])


def _value_score(projection: float, salary: Optional[int]) -> Tuple[float, Optional[float]]:
    if salary is None or salary <= 0:
        return 50.0, None
    points_per_1000 = projection / (salary / cfg.VALUE_MODEL["salary_unit"])
    r = cfg.RANGES["value"]["points_per_1000_salary"]
    return _scale(points_per_1000, r["low"], r["high"], r["invert"]), points_per_1000


def _opponent_k_percent(p: PitcherInput) -> Optional[float]:
    """Prefer a true handedness-specific opponent strikeout rate; fall
    back to the team's overall K% when that's all the Research Engine has
    collected so far (see OpponentStats.strikeout_percent). Both feed the
    same scoring inputs -- only the reason text needs to know which one
    it actually got, so it never claims a hand-specific split it doesn't
    have."""
    if p.opponent_stats.strikeout_percent_vs_hand is not None:
        return p.opponent_stats.strikeout_percent_vs_hand
    return p.opponent_stats.strikeout_percent


# ----------------------------------------------------------------------------
# Risk / confidence
# ----------------------------------------------------------------------------


def _risk_score(p: PitcherInput, features: DerivedFeatures, critical_missing: List[str]) -> float:
    rm = cfg.RISK_MODEL
    risk = rm["base_risk"]
    risk += _linear_penalty(
        features.expected_pitch_count, rm["low_pitch_count_threshold"], rm["low_pitch_count_floor"], rm["low_pitch_count_max_penalty"]
    )
    risk += _linear_penalty(
        features.blended_bb_percent, rm["high_bb_percent_threshold"], rm["high_bb_percent_scale_high"], rm["high_bb_percent_max_penalty"]
    )
    risk += _linear_penalty(
        p.season.barrel_percent, rm["high_barrel_threshold"], rm["high_barrel_scale_high"], rm["high_barrel_max_penalty"]
    )
    risk += _linear_penalty(
        p.opponent_stats.implied_runs, rm["high_implied_runs_threshold"], rm["high_implied_runs_scale_high"], rm["high_implied_runs_max_penalty"]
    )
    risk += _linear_penalty(
        features.velocity_change, rm["velocity_decline_threshold"], rm["velocity_decline_scale_high"], rm["velocity_decline_max_penalty"]
    )
    # Milestone 5: elevated hard-hit rate allowed, and a declining CSW trend
    # (recent worse than season), each add risk on top of the existing
    # barrel/velocity-decline penalties above.
    risk += _linear_penalty(
        p.season.hard_hit_percent, rm["high_hard_hit_threshold"], rm["high_hard_hit_scale_high"], rm["high_hard_hit_max_penalty"]
    )
    risk += _linear_penalty(
        p.trends.csw_trend, rm["csw_decline_threshold"], rm["csw_decline_scale_high"], rm["csw_decline_max_penalty"]
    )
    risk += len(critical_missing) * rm["missing_critical_field_penalty"]
    return _clamp(risk, 0.0, 100.0)


def _confidence_score(p: PitcherInput, critical_missing: List[str], minor_missing: List[str]) -> float:
    """Confidence reflects data COMPLETENESS (the critical/minor field
    counts, as before) and, as of Milestone 5, SAMPLE SIZE: a pitcher
    with 8 innings this season or a single "recent" start has a number in
    every field, but those numbers are far less trustworthy than a
    full-workload starter's. Advanced-metric availability is folded into
    `minor_missing` upstream in `_missing_data` -- it doesn't need a
    separate term here."""
    cm = cfg.CONFIDENCE_MODEL
    confidence = cm["base_confidence"]
    confidence -= len(critical_missing) * cm["critical_missing_penalty"]
    confidence -= len(minor_missing) * cm["minor_missing_penalty"]
    confidence -= _linear_penalty(
        p.season.innings, cm["season_sample_innings_threshold"], cm["season_sample_innings_floor"], cm["season_sample_max_penalty"]
    )
    confidence -= _linear_penalty(
        p.recent.innings, cm["recent_sample_innings_threshold"], cm["recent_sample_innings_floor"], cm["recent_sample_max_penalty"]
    )
    return _clamp(confidence, cm["min_confidence"], 100.0)


# ----------------------------------------------------------------------------
# Tags
# ----------------------------------------------------------------------------


def _tags(p: PitcherInput, features: DerivedFeatures, scores: Dict[str, float]) -> List[str]:
    t = cfg.TAG_THRESHOLDS
    tags: List[str] = []

    if scores["strikeout_score"] >= t["elite_k_upside_score"]:
        tags.append("elite_k_upside")

    opp_k = _opponent_k_percent(p)
    if opp_k is not None and opp_k >= t["strong_k_matchup_opponent_k_percent"]:
        tags.append("strong_k_matchup")

    if features.blended_bb_percent is not None and features.blended_bb_percent <= t["low_walk_rate_bb_percent"]:
        tags.append("low_walk_rate")

    implied_runs = p.opponent_stats.implied_runs
    if (
        implied_runs is not None
        and implied_runs <= t["good_run_environment_implied_runs"]
        and scores["run_prevention_score"] >= t["good_run_environment_score"]
    ):
        tags.append("good_run_environment")

    if features.expected_pitch_count >= t["high_pitch_count"]:
        tags.append("high_pitch_count")

    if scores["value_score"] >= t["salary_value_score"]:
        tags.append("salary_value")

    if features.velocity_change is not None:
        if features.velocity_change >= t["velocity_up"]:
            tags.append("velocity_up")
        elif features.velocity_change <= t["velocity_down"]:
            tags.append("velocity_down")

    dangerous = False
    if p.opponent_stats.woba_vs_hand is not None and p.opponent_stats.woba_vs_hand >= t["dangerous_opponent_woba"]:
        dangerous = True
    if implied_runs is not None and implied_runs >= t["dangerous_opponent_implied_runs"]:
        dangerous = True
    if dangerous:
        tags.append("dangerous_opponent")

    if p.season.barrel_percent is not None and p.season.barrel_percent >= t["high_barrel_risk"]:
        tags.append("high_barrel_risk")

    if features.blended_bb_percent is not None and features.blended_bb_percent >= t["walk_risk_bb_percent"]:
        tags.append("walk_risk")

    if features.expected_pitch_count <= t["limited_workload_pitch_count"]:
        tags.append("limited_workload")

    if (
        scores["strikeout_score"] >= t["ace_profile_strikeout_score"]
        and scores["run_prevention_score"] >= t["ace_profile_run_prevention_score"]
        and scores["workload_score"] >= t["ace_profile_workload_score"]
    ):
        tags.append("ace_profile")

    # --- Milestone 5: Statcast-driven tags --------------------------------
    csw = p.season.csw_percent if p.season.csw_percent is not None else p.recent.csw_percent
    if csw is not None and csw >= t["elite_csw_percent"]:
        tags.append("elite_csw")

    if p.season.swinging_strike_percent is not None and p.season.swinging_strike_percent >= t["elite_swinging_strike_percent"]:
        tags.append("elite_whiffs")

    if (
        p.season.hard_hit_percent is not None and p.season.hard_hit_percent <= t["contact_suppression_hard_hit_max"]
        and p.season.barrel_percent is not None and p.season.barrel_percent <= t["contact_suppression_barrel_max"]
    ):
        tags.append("elite_contact_suppression")

    # Trend-based (distinct from the absolute-level "high_barrel_risk" tag
    # above): flags a barrel/hard-hit rate that's RISING recently, using the
    # same "moved enough to count" bar as the positive/negative_trend tags.
    signal_bar = cfg.TREND_MODEL["signal_threshold"]
    if p.trends.barrel_trend is not None and p.trends.barrel_trend <= -signal_bar:
        tags.append("barrel_risk")
    if p.trends.hard_hit_trend is not None and p.trends.hard_hit_trend <= -signal_bar:
        tags.append("hard_contact_risk")

    if p.season.ground_ball_percent is not None and p.season.ground_ball_percent >= t["ground_ball_specialist_percent"]:
        tags.append("ground_ball_specialist")

    trend_signals = [p.trends.velocity_trend, p.trends.csw_trend, p.trends.swinging_strike_trend, p.trends.hard_hit_trend, p.trends.barrel_trend]
    available_signals = [v for v in trend_signals if v is not None]
    tm = cfg.TREND_MODEL
    if len(available_signals) >= tm["min_signals_available"]:
        positive_count = sum(1 for v in available_signals if v >= signal_bar)
        negative_count = sum(1 for v in available_signals if v <= -signal_bar)
        if positive_count >= tm["min_signals_agreeing"]:
            tags.append("positive_trend")
        elif negative_count >= tm["min_signals_agreeing"]:
            tags.append("negative_trend")

    # "Positive regression" = actual ERA has been worse than the peripherals
    # (xERA) suggest -- the pitcher has been unlucky, so results should
    # improve (regress toward xERA) going forward. "Negative regression" is
    # the opposite: results have outrun the peripherals and are due to worsen.
    if p.season.era is not None and p.season.xera is not None:
        era_minus_xera = p.season.era - p.season.xera
        if era_minus_xera >= t["xera_regression_gap"]:
            tags.append("xERA_positive_regression")
        elif era_minus_xera <= -t["xera_regression_gap"]:
            tags.append("xERA_negative_regression")

    return tags


# ----------------------------------------------------------------------------
# Reasons
# ----------------------------------------------------------------------------


def _hand_label(hand: Optional[str]) -> str:
    if hand == "R":
        return "right-handed"
    if hand == "L":
        return "left-handed"
    return "same-handed"


def _reasons(
    p: PitcherInput,
    features: DerivedFeatures,
    scores: Dict[str, float],
    value_points_per_1000: Optional[float],
    critical_missing: List[str],
    minor_missing: List[str],
    confidence: float,
) -> List[str]:
    candidates: List[Tuple[float, str]] = []

    if p.season.k_percent is not None:
        descriptor = (
            "elite" if scores["strikeout_score"] >= 85 else
            "strong" if scores["strikeout_score"] >= 70 else
            "modest" if scores["strikeout_score"] >= 50 else
            "limited"
        )
        kbb_clause = f" (K-BB% {p.season.k_minus_bb_percent:.1f}%)" if p.season.k_minus_bb_percent is not None else ""
        candidates.append((
            abs(scores["strikeout_score"] - 50.0),
            f"{p.season.k_percent:.1f}% season strikeout rate gives {descriptor} strikeout upside{kbb_clause}.",
        ))

    if p.opponent_stats.strikeout_percent_vs_hand is not None:
        candidates.append((
            abs(scores["matchup_score"] - 50.0),
            f"Opponent strikes out {p.opponent_stats.strikeout_percent_vs_hand:.1f}% of the time against "
            f"{_hand_label(p.throwing_hand)} pitching.",
        ))
    elif p.opponent_stats.strikeout_percent is not None:
        candidates.append((
            abs(scores["matchup_score"] - 50.0),
            f"Opponent strikes out {p.opponent_stats.strikeout_percent:.1f}% of the time overall this season "
            f"(handedness-specific splits not yet available).",
        ))

    implied_runs = p.opponent_stats.implied_runs
    if implied_runs is not None:
        word = "favorable" if implied_runs <= 3.8 else "unfavorable" if implied_runs >= 4.5 else "middling"
        article = "an" if word == "unfavorable" else "a"
        candidates.append((
            abs(implied_runs - 4.25) * 20.0,
            f"Opponent implied total of {implied_runs:.1f} runs creates {article} {word} run-prevention environment.",
        ))

    if features.run_rate_estimator_present:
        label = features.run_rate_estimator_label.split("+")[0].upper()
        value = getattr(p.season, features.run_rate_estimator_label.split("+")[0])
        candidates.append((
            abs(scores["run_prevention_score"] - 50.0),
            f"{label} of {value:.2f} supports a run-prevention score of {scores['run_prevention_score']:.0f}.",
        ))

    if features.velocity_change is not None:
        direction = "down" if features.velocity_change < 0 else "up"
        candidates.append((
            abs(features.velocity_change) * 15.0,
            f"Recent fastball velocity is {direction} {abs(features.velocity_change):.1f} mph from his season level "
            f"({p.recent.season_velocity:.1f} -> {p.recent.velocity:.1f}).",
        ))

    if features.blended_bb_percent is not None:
        tag = (
            "elevated" if features.blended_bb_percent >= 9.0 else
            "well-controlled" if features.blended_bb_percent <= 6.0 else
            "moderate"
        )
        candidates.append((
            abs(features.blended_bb_percent - 7.5) * 4.0,
            f"{features.blended_bb_percent:.1f}% blended walk rate is {tag}.",
        ))

    if p.season.hard_hit_percent is not None or p.season.barrel_percent is not None:
        parts = []
        if p.season.barrel_percent is not None:
            parts.append(f"{p.season.barrel_percent:.1f}% barrel rate")
        if p.season.hard_hit_percent is not None:
            parts.append(f"{p.season.hard_hit_percent:.1f}% hard-hit rate")
        candidates.append((
            abs(scores["contact_score"] - 50.0) * 0.6,
            f"{' and '.join(parts)} shape a contact-quality score of {scores['contact_score']:.0f}.",
        ))

    # Milestone 5: CSW is only available at the recent (last-3-starts) grain
    # this milestone -- see research/statcast_enrichment.py's module docstring.
    csw_value = p.season.csw_percent if p.season.csw_percent is not None else p.recent.csw_percent
    if csw_value is not None:
        scope = "season" if p.season.csw_percent is not None else "recent, last 3 starts"
        descriptor = (
            "ranks among the best marks in baseball" if csw_value >= cfg.TAG_THRESHOLDS["elite_csw_percent"] else
            "is a solid, roughly average mark" if csw_value >= 27.0 else
            "trails league average"
        )
        candidates.append((
            abs(csw_value - 28.5) * 3.0,
            f"{csw_value:.1f}% CSW ({scope}) {descriptor}.",
        ))

    barrel_cap = cfg.TAG_THRESHOLDS["contact_suppression_barrel_max"]
    if p.season.barrel_percent is not None and p.season.barrel_percent <= barrel_cap:
        candidates.append((
            (barrel_cap - p.season.barrel_percent) * 8.0,
            f"Barrel rate allowed remains under {barrel_cap:.0f}% ({p.season.barrel_percent:.1f}%), a strong sign of contact suppression.",
        ))

    if p.season.era is not None and p.season.xera is not None:
        era_minus_xera = p.season.era - p.season.xera
        if abs(era_minus_xera) >= 0.15:
            comparison = "lower" if era_minus_xera > 0 else "higher"
            quality = "better" if era_minus_xera > 0 else "worse"
            candidates.append((
                abs(era_minus_xera) * 25.0,
                f"xERA ({p.season.xera:.2f}) is significantly {comparison} than traditional ERA ({p.season.era:.2f}), "
                f"suggesting {quality} underlying performance than the results show.",
            ))

    # Always available: workload is always resolved (default fallback if needed).
    candidates.append((
        abs(scores["workload_score"] - 50.0) * 0.6,
        f"Expected pitch count of {features.expected_pitch_count:.0f} ({features.workload_source_label}) "
        f"projects to roughly {features.expected_innings:.1f} innings.",
    ))

    # Always available: projection/value are always computed.
    if value_points_per_1000 is not None:
        candidates.append((
            abs(scores["value_score"] - 50.0) * 0.5,
            f"Projects {value_points_per_1000:.2f} DK points per $1,000 salary (value score {scores['value_score']:.0f}).",
        ))

    if confidence < 75:
        candidates.append((
            100.0,
            f"Confidence reduced to {confidence:.0f} due to {len(critical_missing)} missing critical and "
            f"{len(minor_missing)} missing secondary inputs.",
        ))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return [text for _, text in candidates[:6]]


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def analyze_pitcher(p: PitcherInput) -> PitcherBoardEntry:
    """Score a single normalized pitcher into a full board entry."""
    features = _derive_features(p)
    critical_missing, minor_missing = _missing_data(p, features)
    scores = _sub_scores(p, features)

    projection = _projection(features)
    risk_score = _risk_score(p, features, critical_missing)
    confidence = _confidence_score(p, critical_missing, minor_missing)
    ceiling = _ceiling(projection, scores)
    floor = _floor(projection, risk_score)
    value_score, value_points_per_1000 = _value_score(projection, p.salary)
    scores["value_score"] = value_score

    overall_score = sum(cfg.OVERALL_WEIGHTS[key] * scores[key] for key in cfg.OVERALL_WEIGHTS)

    tags = _tags(p, features, scores)
    reasons = _reasons(p, features, scores, value_points_per_1000, critical_missing, minor_missing, confidence)

    return PitcherBoardEntry(
        player_id=p.player_id,
        name=p.name,
        team=p.team,
        opponent=p.opponent,
        salary=p.salary,
        projection=round(projection, 1),
        ceiling=round(ceiling, 1),
        floor=round(floor, 1),
        overall_score=round(overall_score, 1),
        strikeout_score=round(scores["strikeout_score"], 1),
        run_prevention_score=round(scores["run_prevention_score"], 1),
        matchup_score=round(scores["matchup_score"], 1),
        workload_score=round(scores["workload_score"], 1),
        contact_score=round(scores["contact_score"], 1),
        environment_score=round(scores["environment_score"], 1),
        value_score=round(value_score, 1),
        risk_score=round(risk_score, 1),
        confidence=round(confidence, 1),
        tags=tags,
        reasons=reasons,
    )


def _add_slate_relative_reasons(board: List[PitcherBoardEntry], pitchers: List[PitcherInput]) -> None:
    """Slate-wide context (e.g. "CSW ranks 2nd of 30 on today's slate")
    can only be computed once every pitcher on the slate has been scored,
    so it can't live in `_reasons` (which only ever sees one pitcher at a
    time, and stays independently testable/usable that way). Mutates
    `board` entries in place -- a bonus reason, never a required one."""
    sc = cfg.SLATE_CONTEXT
    pitchers_by_id = {p.player_id: p for p in pitchers}

    ranked = sorted(
        (
            (entry, pitchers_by_id[entry.player_id].season.csw_percent)
            for entry in board
            if pitchers_by_id[entry.player_id].season.csw_percent is not None
        ),
        key=lambda pair: -pair[1],
    )
    if len(ranked) < sc["min_slate_size_for_ranking"]:
        return

    for rank, (entry, csw) in enumerate(ranked[: sc["top_rank_cutoff"]], start=1):
        reason = f"{csw:.1f}% season CSW ranks {rank} of {len(ranked)} on today's slate."
        # `_reasons` already fills up to its own 6-item cap for almost any
        # populated pitcher, so simply appending here would silently never
        # fire. Slate ranking in the top 3 is a strong enough signal to
        # outrank the single weakest existing reason instead of being
        # dropped for being late to the list.
        if len(entry.reasons) < 6:
            entry.reasons.append(reason)
        else:
            entry.reasons[-1] = reason


def analyze_slate(pitchers: List[PitcherInput]) -> List[PitcherBoardEntry]:
    """Score a full slate and return a deterministically ranked board."""
    board = [analyze_pitcher(p) for p in pitchers]
    board.sort(key=lambda entry: (-entry.overall_score, -entry.projection, entry.player_id))
    _add_slate_relative_reasons(board, pitchers)
    return board
