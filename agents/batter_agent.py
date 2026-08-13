"""Batter Agent: deterministic scoring for starting-lineup hitters.

Mirrors agents/pitcher_agent.py's architecture and philosophy exactly:
every number here comes from transparent, testable Python logic over
`BatterInput` fields. Nothing here calls the network, calls MLB/Baseball
Savant, or imports agents.pitcher_agent or evaluation/ -- see
tests/test_architecture_separation.py, which now also guards this
module.

Missing non-critical stats are tolerated (the affected sub-score
renormalizes over whatever is present); missing critical stats lower
confidence and raise risk. Nothing is ever invented to fill a gap.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import batter_scoring_config as cfg
from models.batter import BatterBoardEntry, BatterInput, PlatoonSplitStats

# ----------------------------------------------------------------------------
# Small numeric helpers (own copies -- see research/statcast_collector.py's
# and research/statcast_enrichment.py's identical precedent for why: keeps
# this agent fully decoupled from agents/pitcher_agent.py).
# ----------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _scale(value: Optional[float], low: float, high: float, invert: bool = False) -> Optional[float]:
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
    if value is None:
        return 0.0
    span = extreme - start
    if span == 0:
        return 0.0
    pct = (value - start) / span
    pct = _clamp(pct, 0.0, 1.0)
    return pct * max_penalty


def _composite_score(purpose: str, raw_values: Dict[str, Optional[float]]) -> Tuple[float, List[str]]:
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
    expected_pa: float
    relevant_platoon: PlatoonSplitStats
    platoon_woba: Optional[float]
    hit_distribution_source: str
    expected_singles: float
    expected_doubles: float
    expected_triples: float
    expected_home_runs: float
    expected_walks: float
    expected_stolen_bases: float
    expected_strikeouts: float


def _derive_features(b: BatterInput) -> DerivedFeatures:
    pm = cfg.PROJECTION_MODEL

    blended_k_percent = _blend(b.season.k_percent, b.recent.k_percent, pm["season_k_weight"], pm["recent_k_weight"])
    blended_bb_percent = _blend(b.season.bb_percent, b.recent.bb_percent, pm["season_bb_weight"], pm["recent_bb_weight"])

    if b.batting_order is not None:
        expected_pa = pm["expected_pa_by_order"].get(b.batting_order, pm["default_expected_pa"])
    else:
        expected_pa = pm["default_expected_pa"]

    hand = b.opposing_pitcher.throwing_hand
    if hand == "L":
        relevant_platoon = b.vs_lhp
    elif hand == "R":
        relevant_platoon = b.vs_rhp
    else:
        relevant_platoon = PlatoonSplitStats()
    platoon_woba = relevant_platoon.woba

    hits = b.season.hits or 0
    if hits > 0:
        double_share = (b.season.doubles or 0) / hits
        triple_share = (b.season.triples or 0) / hits
        hr_share = (b.season.home_runs or 0) / hits
        hit_distribution_source = "player"
    else:
        double_share = pm["league_avg_double_share_of_hits"]
        triple_share = pm["league_avg_triple_share_of_hits"]
        hr_share = pm["league_avg_hr_share_of_hits"]
        hit_distribution_source = "league_average_fallback"

    k_rate = (blended_k_percent if blended_k_percent is not None else pm["league_avg_k_percent"]) / 100.0
    bb_rate = (blended_bb_percent if blended_bb_percent is not None else pm["league_avg_bb_percent"]) / 100.0
    avg = b.season.avg if b.season.avg is not None else pm["league_avg_avg"]

    expected_walks = expected_pa * bb_rate
    expected_strikeouts = expected_pa * k_rate
    at_bat_like = max(expected_pa - expected_walks, 0.0)
    expected_hits = at_bat_like * avg
    expected_home_runs = expected_hits * hr_share
    expected_doubles = expected_hits * double_share
    expected_triples = expected_hits * triple_share
    expected_singles = max(expected_hits - expected_home_runs - expected_doubles - expected_triples, 0.0)

    if b.season.stolen_bases is not None and b.season.plate_appearances:
        sb_rate = b.season.stolen_bases / b.season.plate_appearances
    else:
        sb_rate = pm["league_avg_sb_per_pa"]
    expected_stolen_bases = expected_pa * sb_rate

    return DerivedFeatures(
        blended_k_percent=blended_k_percent,
        blended_bb_percent=blended_bb_percent,
        expected_pa=expected_pa,
        relevant_platoon=relevant_platoon,
        platoon_woba=platoon_woba,
        hit_distribution_source=hit_distribution_source,
        expected_singles=expected_singles,
        expected_doubles=expected_doubles,
        expected_triples=expected_triples,
        expected_home_runs=expected_home_runs,
        expected_walks=expected_walks,
        expected_stolen_bases=expected_stolen_bases,
        expected_strikeouts=expected_strikeouts,
    )


# ----------------------------------------------------------------------------
# Missing-data accounting (drives risk + confidence)
# ----------------------------------------------------------------------------


def _missing_data(b: BatterInput, features: DerivedFeatures) -> Tuple[List[str], List[str]]:
    critical_checks = [
        ("season_k_percent", b.season.k_percent is not None),
        ("season_bb_percent", b.season.bb_percent is not None),
        ("season_avg", b.season.avg is not None),
        ("batting_order", b.batting_order is not None),
        ("opposing_pitcher", b.opposing_pitcher.player_id is not None),
    ]
    minor_checks = [
        ("xwoba", b.season.xwoba is not None),
        ("xba", b.season.xba is not None),
        ("hard_hit_percent", b.season.hard_hit_percent is not None),
        ("barrel_percent", b.season.barrel_percent is not None),
        ("exit_velocity", b.season.exit_velocity is not None),
        ("bat_speed", b.season.bat_speed is not None),
        ("recent_data", b.recent.plate_appearances is not None),
        ("platoon_split", features.platoon_woba is not None),
        ("batting_hand", b.batting_hand is not None),
        ("opposing_pitcher_xera", b.opposing_pitcher.xera is not None),
        ("opposing_pitcher_hard_hit_allowed", b.opposing_pitcher.hard_hit_percent_allowed is not None),
    ]
    critical_missing = [name for name, present in critical_checks if not present]
    minor_missing = [name for name, present in minor_checks if not present]
    return critical_missing, minor_missing


# ----------------------------------------------------------------------------
# Sub-scores
# ----------------------------------------------------------------------------


def _sub_scores(b: BatterInput, features: DerivedFeatures) -> Dict[str, float]:
    hitting_skill_score, _ = _composite_score("hitting_skill", {
        "xwoba": b.season.xwoba,
        "woba": b.season.woba,
        "xslg": b.season.xslg,
        "iso": b.season.iso,
        "barrel_percent": b.season.barrel_percent,
        "hard_hit_percent": b.season.hard_hit_percent,
        "exit_velocity": b.season.exit_velocity,
    })

    power_score, _ = _composite_score("power", {
        "iso": b.season.iso,
        "xslg": b.season.xslg,
        "barrel_percent": b.season.barrel_percent,
        "hard_hit_percent": b.season.hard_hit_percent,
        "exit_velocity": b.season.exit_velocity,
    })

    contact_score, _ = _composite_score("contact", {
        "k_percent": features.blended_k_percent,
        "bb_percent": features.blended_bb_percent,
        "xba": b.season.xba,
    })

    matchup_score, _ = _composite_score("matchup", {
        "pitcher_k_percent": b.opposing_pitcher.k_percent,
        "pitcher_xwoba_allowed": b.opposing_pitcher.xwoba_allowed,
        "pitcher_hard_hit_allowed": b.opposing_pitcher.hard_hit_percent_allowed,
        "platoon_woba": features.platoon_woba,
    })

    recent_trend_score, _ = _composite_score("recent_trend", {
        "exit_velocity_trend": b.trends.exit_velocity_trend,
        "hard_hit_trend": b.trends.hard_hit_trend,
        "barrel_trend": b.trends.barrel_trend,
        "xwoba_trend": b.trends.xwoba_trend,
        "strikeout_rate_trend": b.trends.strikeout_rate_trend,
    })

    lineup_position_score, _ = _composite_score("lineup_position", {
        "batting_order": float(b.batting_order) if b.batting_order is not None else None,
    })

    # Weather/park/Vegas/umpire analysis does not exist yet -- neutral,
    # explicitly not pretending otherwise (see CLAUDE.md).
    environment_score = 50.0

    return {
        "hitting_skill_score": hitting_skill_score,
        "power_score": power_score,
        "contact_score": contact_score,
        "matchup_score": matchup_score,
        "recent_trend_score": recent_trend_score,
        "lineup_position_score": lineup_position_score,
        "environment_score": environment_score,
    }


# ----------------------------------------------------------------------------
# Projection / ceiling / floor / value
# ----------------------------------------------------------------------------


def _projection(features: DerivedFeatures) -> float:
    dk = cfg.DK_HITTER_SCORING
    points = (
        features.expected_singles * dk["single"]
        + features.expected_doubles * dk["double"]
        + features.expected_triples * dk["triple"]
        + features.expected_home_runs * dk["home_run"]
        + features.expected_walks * dk["walk"]
        + features.expected_stolen_bases * dk["stolen_base"]
    )
    return max(points, 0.0)


def _ceiling(projection: float, scores: Dict[str, float]) -> float:
    cm = cfg.CEILING_MODEL
    return projection + (
        (scores["power_score"] / 100.0) * cm["power_bonus_max"]
        + (scores["matchup_score"] / 100.0) * cm["matchup_bonus_max"]
        + (scores["lineup_position_score"] / 100.0) * cm["lineup_position_bonus_max"]
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


# ----------------------------------------------------------------------------
# Risk / confidence
# ----------------------------------------------------------------------------


def _risk_score(b: BatterInput, features: DerivedFeatures, matchup_score: float, critical_missing: List[str]) -> float:
    rm = cfg.RISK_MODEL
    risk = rm["base_risk"]
    risk += _linear_penalty(
        features.blended_k_percent, rm["high_k_percent_threshold"], rm["high_k_percent_scale_high"], rm["high_k_percent_max_penalty"]
    )
    risk += _linear_penalty(
        float(b.batting_order) if b.batting_order is not None else None,
        rm["poor_lineup_slot_threshold"], rm["poor_lineup_slot_scale_high"], rm["poor_lineup_slot_max_penalty"],
    )
    risk += _linear_penalty(
        float(b.season.plate_appearances) if b.season.plate_appearances is not None else None,
        rm["small_sample_pa_threshold"], rm["small_sample_pa_floor"], rm["small_sample_max_penalty"],
    )
    risk += _linear_penalty(
        matchup_score, rm["weak_matchup_threshold"], rm["weak_matchup_scale_low"], rm["weak_matchup_max_penalty"]
    )
    if (
        b.season.iso is not None and b.season.iso >= rm["volatile_power_iso_threshold"]
        and features.blended_k_percent is not None and features.blended_k_percent >= rm["volatile_power_k_percent_threshold"]
    ):
        risk += rm["volatile_power_flat_penalty"]
    risk += len(critical_missing) * rm["missing_critical_field_penalty"]
    return _clamp(risk, 0.0, 100.0)


def _confidence_score(b: BatterInput, critical_missing: List[str], minor_missing: List[str]) -> float:
    cm = cfg.CONFIDENCE_MODEL
    confidence = cm["base_confidence"]
    confidence -= len(critical_missing) * cm["critical_missing_penalty"]
    confidence -= len(minor_missing) * cm["minor_missing_penalty"]
    confidence -= _linear_penalty(
        float(b.season.plate_appearances) if b.season.plate_appearances is not None else None,
        cm["season_sample_pa_threshold"], cm["season_sample_pa_floor"], cm["season_sample_max_penalty"],
    )
    confidence -= _linear_penalty(
        float(b.recent.plate_appearances) if b.recent.plate_appearances is not None else None,
        cm["recent_sample_pa_threshold"], cm["recent_sample_pa_floor"], cm["recent_sample_max_penalty"],
    )
    return _clamp(confidence, cm["min_confidence"], 100.0)


# ----------------------------------------------------------------------------
# Tags
# ----------------------------------------------------------------------------


def _tags(b: BatterInput, features: DerivedFeatures, scores: Dict[str, float]) -> List[str]:
    t = cfg.TAG_THRESHOLDS
    tags: List[str] = []

    if b.season.iso is not None and b.season.iso >= t["elite_power_iso"]:
        tags.append("elite_power")
    if b.season.barrel_percent is not None and b.season.barrel_percent >= t["elite_barrel_percent"]:
        tags.append("elite_barrel")
    if b.season.hard_hit_percent is not None and b.season.hard_hit_percent >= t["elite_hard_hit_percent"]:
        tags.append("elite_hard_hit")
    if b.season.xwoba is not None and b.season.xwoba >= t["elite_xwoba"]:
        tags.append("elite_xwoba")

    if features.blended_k_percent is not None and features.blended_k_percent <= t["low_strikeout_k_percent"]:
        tags.append("low_strikeout")
    if features.blended_bb_percent is not None and features.blended_bb_percent >= t["walk_upside_bb_percent"]:
        tags.append("walk_upside")

    if features.platoon_woba is not None and b.season.xwoba is not None:
        gap = features.platoon_woba - b.season.xwoba
        if gap >= 0.020:
            tags.append("platoon_advantage")
        elif gap <= -0.020:
            tags.append("platoon_disadvantage")

    if b.batting_order is not None:
        if b.batting_order == t["leadoff_order"]:
            tags.append("leadoff")
        if b.batting_order <= t["top_order_max"]:
            tags.append("top_order")
        if b.batting_order == t["cleanup_order"]:
            tags.append("cleanup_hitter")
        if b.batting_order >= t["bottom_order_min"]:
            tags.append("bottom_order")

    if scores["recent_trend_score"] >= t["hot_statcast_score"]:
        tags.append("hot_statcast")
    elif scores["recent_trend_score"] <= t["cold_statcast_score"]:
        tags.append("cold_statcast")

    if (
        b.recent.hard_hit_percent is not None and b.recent.hard_hit_percent >= t["power_sleeper_recent_hard_hit"]
        and b.season.iso is not None and b.season.iso <= t["power_sleeper_season_iso_max"]
    ):
        tags.append("power_sleeper")

    if features.blended_k_percent is not None and features.blended_k_percent >= t["high_k_risk_k_percent"]:
        tags.append("high_k_risk")

    if scores["matchup_score"] <= t["tough_pitcher_matchup_score"]:
        tags.append("tough_pitcher_matchup")
    elif scores["matchup_score"] >= t["strong_pitcher_matchup_score"]:
        tags.append("strong_pitcher_matchup")

    trend_signals = [
        b.trends.exit_velocity_trend, b.trends.hard_hit_trend, b.trends.barrel_trend,
        b.trends.xwoba_trend, b.trends.strikeout_rate_trend,
    ]
    available_signals = [v for v in trend_signals if v is not None]
    tm = cfg.TREND_MODEL
    signal_bar = tm["signal_threshold"]
    if len(available_signals) >= tm["min_signals_available"]:
        positive_count = sum(1 for v in available_signals if v >= signal_bar)
        negative_count = sum(1 for v in available_signals if v <= -signal_bar)
        if positive_count >= tm["min_signals_agreeing"]:
            tags.append("positive_contact_trend")
        elif negative_count >= tm["min_signals_agreeing"]:
            tags.append("negative_contact_trend")

    return tags


# ----------------------------------------------------------------------------
# Reasons
# ----------------------------------------------------------------------------


def _reasons(
    b: BatterInput,
    features: DerivedFeatures,
    scores: Dict[str, float],
    value_points_per_1000: Optional[float],
    critical_missing: List[str],
    minor_missing: List[str],
    confidence: float,
) -> List[str]:
    candidates: List[Tuple[float, str]] = []

    if b.season.barrel_percent is not None:
        descriptor = "one of the strongest power profiles on the slate" if b.season.barrel_percent >= cfg.TAG_THRESHOLDS["elite_barrel_percent"] else "a solid power profile" if b.season.barrel_percent >= 8.0 else "a modest power profile"
        candidates.append((
            abs(scores["power_score"] - 50.0),
            f"{b.season.barrel_percent:.1f}% barrel rate gives him {descriptor}.",
        ))

    if b.batting_order is not None:
        candidates.append((
            abs(scores["lineup_position_score"] - 50.0),
            f"He is batting {b.batting_order}{'st' if b.batting_order == 1 else 'nd' if b.batting_order == 2 else 'rd' if b.batting_order == 3 else 'th'}, "
            f"{'increasing' if b.batting_order <= 5 else 'limiting'} expected plate-appearance opportunity.",
        ))

    if b.trends.hard_hit_trend is not None and b.recent.hard_hit_percent is not None and b.season.hard_hit_percent is not None:
        direction = "above" if b.trends.hard_hit_trend >= 0 else "below"
        candidates.append((
            abs(b.trends.hard_hit_trend) * 3.0,
            f"His recent hard-hit rate is {abs(b.trends.hard_hit_trend):.1f} percentage points {direction} his season rate "
            f"({b.recent.hard_hit_percent:.1f}% vs {b.season.hard_hit_percent:.1f}%).",
        ))

    if b.opposing_pitcher.player_id is not None and b.opposing_pitcher.xwoba_allowed is not None:
        hand_label = "right-handed" if b.opposing_pitcher.throwing_hand == "R" else "left-handed" if b.opposing_pitcher.throwing_hand == "L" else "same-handed"
        candidates.append((
            abs(scores["matchup_score"] - 50.0),
            f"He faces a {hand_label} pitcher who has allowed a {b.opposing_pitcher.xwoba_allowed:.3f} xwOBA.",
        ))

    if b.season.xwoba is not None:
        descriptor = "elite" if b.season.xwoba >= cfg.TAG_THRESHOLDS["elite_xwoba"] else "strong" if b.season.xwoba >= 0.340 else "average" if b.season.xwoba >= 0.310 else "below-average"
        candidates.append((
            abs(scores["hitting_skill_score"] - 50.0),
            f"{b.season.xwoba:.3f} season xwOBA reflects {descriptor} underlying hitting skill.",
        ))

    if features.blended_k_percent is not None:
        tag = "low" if features.blended_k_percent <= cfg.TAG_THRESHOLDS["low_strikeout_k_percent"] else "elevated" if features.blended_k_percent >= cfg.TAG_THRESHOLDS["high_k_risk_k_percent"] else "moderate"
        candidates.append((
            abs(features.blended_k_percent - 22.0) * 2.0,
            f"{features.blended_k_percent:.1f}% blended strikeout rate is {tag}.",
        ))

    if features.platoon_woba is not None and b.opposing_pitcher.throwing_hand is not None:
        hand_label = "RHP" if b.opposing_pitcher.throwing_hand == "R" else "LHP"
        candidates.append((
            abs(scores["matchup_score"] - 50.0) * 0.8,
            f"He carries a {features.platoon_woba:.3f} wOBA vs {hand_label} this season.",
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


def analyze_batter(b: BatterInput) -> BatterBoardEntry:
    """Score a single normalized hitter into a full board entry."""
    features = _derive_features(b)
    critical_missing, minor_missing = _missing_data(b, features)
    scores = _sub_scores(b, features)

    projection = _projection(features)
    risk_score = _risk_score(b, features, scores["matchup_score"], critical_missing)
    confidence = _confidence_score(b, critical_missing, minor_missing)
    ceiling = _ceiling(projection, scores)
    floor = _floor(projection, risk_score)
    value_score, value_points_per_1000 = _value_score(projection, b.salary)
    scores["value_score"] = value_score

    overall_score = sum(cfg.OVERALL_WEIGHTS[key] * scores[key] for key in cfg.OVERALL_WEIGHTS)

    tags = _tags(b, features, scores)
    reasons = _reasons(b, features, scores, value_points_per_1000, critical_missing, minor_missing, confidence)

    return BatterBoardEntry(
        player_id=b.player_id,
        name=b.name,
        team=b.team,
        opponent=b.opponent,
        batting_order=b.batting_order,
        salary=b.salary,
        projection=round(projection, 1),
        ceiling=round(ceiling, 1),
        floor=round(floor, 1),
        overall_score=round(overall_score, 1),
        hitting_skill_score=round(scores["hitting_skill_score"], 1),
        power_score=round(scores["power_score"], 1),
        contact_score=round(scores["contact_score"], 1),
        matchup_score=round(scores["matchup_score"], 1),
        recent_trend_score=round(scores["recent_trend_score"], 1),
        lineup_position_score=round(scores["lineup_position_score"], 1),
        environment_score=round(scores["environment_score"], 1),
        value_score=round(value_score, 1),
        risk_score=round(risk_score, 1),
        confidence=round(confidence, 1),
        tags=tags,
        reasons=reasons,
    )


def analyze_slate(batters: List[BatterInput]) -> List[BatterBoardEntry]:
    """Score a full slate and return a deterministically ranked board."""
    board = [analyze_batter(b) for b in batters]
    board.sort(key=lambda entry: (-entry.overall_score, -entry.projection, entry.player_id))
    return board
