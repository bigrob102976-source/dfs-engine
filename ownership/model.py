"""Orchestrates the ownership model: builds features, computes a
transparent weighted raw popularity score per player, normalizes each
player-type pool to its DK-roster-implied total ownership (see
config/dk_roster_config.py -- NOT a hardcoded 200%/800%), then derives
chalk score, leverage score, tier, confidence, tags, and reasons.

No machine learning, no fitting to any slate's outcomes -- every weight
lives in config/ownership_config.py, set by hand.
"""

from typing import Dict, List, Tuple

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_ROSTER_SIZE
from config.ownership_config import (
    CHALK_SCORE_WEIGHTS,
    HITTER_OWNERSHIP_WEIGHTS,
    MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE,
    OWNERSHIP_CONFIDENCE_WEIGHTS,
    OWNERSHIP_MODEL_VERSION,
    OWNERSHIP_TIER_THRESHOLDS,
    PITCHER_OWNERSHIP_WEIGHTS,
    SLATE_SIZE_FULL_CONFIDENCE_HITTER_COUNT,
)
from ownership import features as feature_builder
from ownership.leverage import assign_leverage_tags, compute_leverage_score, compute_quality_percentile
from ownership.models import OwnershipInputPlayer, OwnershipProjection, TeamPopularity
from ownership.slate_normalization import compute_percentiles, normalize_with_cap


def _pitcher_slot_count() -> int:
    return next(s["count"] for s in DK_CLASSIC_ROSTER_SLOTS if s["slot"] == "P")


def _weighted_score(feature_values: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(feature_values[name] * weight for name, weight in weights.items())


def _ownership_tier(pct: float) -> str:
    for name, low, high in OWNERSHIP_TIER_THRESHOLDS:
        if low <= pct < high:
            return name
    return OWNERSHIP_TIER_THRESHOLDS[-1][0]


def _position_comparable_count(player: OwnershipInputPlayer, hitters: List[OwnershipInputPlayer]) -> int:
    position = player.dk_positions[0] if player.dk_positions else None
    if position is None:
        return 0
    return sum(1 for h in hitters if position in h.dk_positions and h.dk_player_id != player.dk_player_id)


def _ownership_confidence(player: OwnershipInputPlayer, comparable_count: int,
                           lineup_completeness_fraction: float, slate_size_fraction: float) -> float:
    w = OWNERSHIP_CONFIDENCE_WEIGHTS
    comparable_factor = min(1.0, comparable_count / MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE) * 100.0
    input_completeness = 100.0 if (
        player.projection is not None and player.ceiling is not None and player.salary and player.confidence is not None
    ) else 40.0
    raw = (
        w["slate_size_factor"] * slate_size_fraction * 100.0
        + w["lineup_completeness_factor"] * lineup_completeness_fraction * 100.0
        + w["comparable_players_factor"] * comparable_factor
        + w["input_completeness_factor"] * input_completeness
    )
    return round(min(100.0, max(0.0, raw)), 2)


def _reasons(player_type: str, f: Dict[str, float], ownership_tier: str) -> List[str]:
    reasons: List[str] = []
    if f["projection_percentile"] >= 80:
        reasons.append(f"Ranks in the top tier of {player_type}s in projection on this slate.")
    if f["value_percentile"] >= 80:
        reasons.append("Strong salary-adjusted value relative to the rest of the slate.")
    if player_type == "pitcher" and f.get("salary_savings_percentile", 0) >= 75:
        reasons.append("Projects similarly to more expensive pitchers, increasing salary-based popularity.")
    if player_type == "pitcher" and f.get("opponent_weakness_percentile", 0) >= 75:
        reasons.append("Favorable matchup against one of the weaker projected offenses on the slate.")
    if player_type == "hitter" and f.get("batting_order_effect", 0) >= 85:
        reasons.append("Batting near the top of the order, increasing expected plate-appearance-driven popularity.")
    if player_type == "hitter" and f.get("team_popularity", 0) >= 80:
        reasons.append("Part of one of the highest-rated offenses on the slate.")
    if player_type == "hitter" and f.get("position_scarcity", 0) >= 70:
        reasons.append("Limited attractive alternatives at this position increase projected popularity.")
    if f["salary_percentile"] >= 80 and f["ceiling_percentile"] >= 70 and f["projection_percentile"] < 60:
        reasons.append("Strong ceiling but expensive salary may limit projected field exposure.")
    if not reasons:
        if ownership_tier in ("very_low", "low"):
            reasons.append("Modest projection and value relative to the rest of the slate keep projected ownership low.")
        else:
            reasons.append("Middle-of-the-pack projection and value relative to the rest of the slate.")
    return reasons[:6]


def _build_projection(
    player: OwnershipInputPlayer, f: Dict[str, float], owned: float, own_pct: float,
    comparable_count: int, lineup_completeness_fraction: float, slate_size_fraction: float,
    secondary_percentile_key: str, team_popularity_for_chalk: float,
) -> OwnershipProjection:
    quality_pct = compute_quality_percentile(f["projection_percentile"], f["ceiling_percentile"], f["overall_score_percentile"])
    leverage = compute_leverage_score(quality_pct, own_pct)
    tier = _ownership_tier(owned)
    chalk = _weighted_score(
        {
            "ownership_percentile": own_pct, "projection_percentile": f["projection_percentile"],
            "value_percentile": f["value_percentile"], "secondary_percentile": f[secondary_percentile_key],
            "team_popularity": team_popularity_for_chalk,
        },
        CHALK_SCORE_WEIGHTS,
    )
    tags = assign_leverage_tags(leverage, owned, f["ceiling_percentile"], quality_pct, tier)
    confidence = _ownership_confidence(player, comparable_count, lineup_completeness_fraction, slate_size_fraction)
    reasons = _reasons(player.player_type, f, tier)

    return OwnershipProjection(
        dk_player_id=player.dk_player_id, mlb_player_id=player.mlb_player_id, name=player.name, team=player.team,
        opponent=player.opponent, player_type=player.player_type, dk_positions=list(player.dk_positions),
        salary=player.salary, projection=player.projection, ceiling=player.ceiling, overall_score=player.overall_score,
        risk_score=player.risk_score, confidence=player.confidence, projected_ownership=owned,
        ownership_confidence=confidence, chalk_score=round(chalk, 2), leverage_score=round(leverage, 2),
        ownership_tier=tier, batting_order=player.batting_order, feature_breakdown=dict(f), reasons=reasons,
        tags=tags, model_version=OWNERSHIP_MODEL_VERSION,
    )


def build_ownership_projections(
    active_pitchers: List[OwnershipInputPlayer], active_hitters: List[OwnershipInputPlayer],
    posted_lineup_hitter_fraction: float,
) -> Tuple[List[OwnershipProjection], Dict[str, TeamPopularity], dict]:
    """`posted_lineup_hitter_fraction` is the fraction of the FULL saved
    pool (including non-active rows) whose lineup is confirmed -- only
    the caller (which sees the whole pool, not just the active subset)
    can compute that; it feeds ownership_confidence's
    "availability of all starting lineups" signal."""
    team_popularity = feature_builder.compute_team_popularity(active_hitters)
    pitcher_features = feature_builder.build_pitcher_features(active_pitchers, team_popularity)
    hitter_features = feature_builder.build_hitter_features(active_hitters, team_popularity)

    raw_pitcher_scores = {
        p.dk_player_id: _weighted_score(pitcher_features[p.dk_player_id], PITCHER_OWNERSHIP_WEIGHTS)
        for p in active_pitchers
    }
    raw_hitter_scores = {
        h.dk_player_id: _weighted_score(hitter_features[h.dk_player_id], HITTER_OWNERSHIP_WEIGHTS)
        * feature_builder.sample_size_dampening(h)
        for h in active_hitters
    }

    pitcher_slot_count = _pitcher_slot_count()
    hitter_slot_count = DK_ROSTER_SIZE - pitcher_slot_count
    target_pitcher_sum = pitcher_slot_count * 100.0
    target_hitter_sum = hitter_slot_count * 100.0

    pitcher_ownership = normalize_with_cap(raw_pitcher_scores, target_pitcher_sum)
    hitter_ownership = normalize_with_cap(raw_hitter_scores, target_hitter_sum)

    pitcher_ownership_pct = compute_percentiles(list(pitcher_ownership.items()))
    hitter_ownership_pct = compute_percentiles(list(hitter_ownership.items()))

    slate_size_fraction = min(1.0, (len(active_hitters) + len(active_pitchers)) / SLATE_SIZE_FULL_CONFIDENCE_HITTER_COUNT)

    projections: List[OwnershipProjection] = []

    for p in active_pitchers:
        owned = round(pitcher_ownership.get(p.dk_player_id, 0.0), 2)
        own_pct = pitcher_ownership_pct.get(p.dk_player_id, 50.0)
        comparable = len(active_pitchers) - 1
        projections.append(_build_projection(
            p, pitcher_features[p.dk_player_id], owned, own_pct, comparable, posted_lineup_hitter_fraction,
            slate_size_fraction, secondary_percentile_key="salary_savings_percentile", team_popularity_for_chalk=50.0,
        ))

    for h in active_hitters:
        owned = round(hitter_ownership.get(h.dk_player_id, 0.0), 2)
        own_pct = hitter_ownership_pct.get(h.dk_player_id, 50.0)
        comparable = _position_comparable_count(h, active_hitters)
        team_stats = team_popularity.get(h.team)
        projections.append(_build_projection(
            h, hitter_features[h.dk_player_id], owned, own_pct, comparable, posted_lineup_hitter_fraction,
            slate_size_fraction, secondary_percentile_key="position_scarcity",
            team_popularity_for_chalk=team_stats.team_popularity_score if team_stats else 50.0,
        ))

    for team, stats in team_popularity.items():
        stats.aggregate_projected_ownership = round(
            sum(o.projected_ownership for o in projections if o.team == team and o.player_type == "hitter"), 2
        )

    normalization_report = {
        "pitcher_ownership_sum": round(sum(pitcher_ownership.values()), 2),
        "pitcher_ownership_expected": target_pitcher_sum,
        "hitter_ownership_sum": round(sum(hitter_ownership.values()), 2),
        "hitter_ownership_expected": target_hitter_sum,
        "players_above_100": sum(1 for o in projections if o.projected_ownership > 100.0),
        "players_below_0": sum(1 for o in projections if o.projected_ownership < 0.0),
    }

    return projections, team_popularity, normalization_report
