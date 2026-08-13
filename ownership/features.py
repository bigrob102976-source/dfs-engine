"""Builds slate-relative ownership features for pitchers and hitters.

Every feature here is derived from information the Research Engine and
Pitcher/Batter Agents already produced pregame (projection, ceiling,
salary, overall_score, confidence, tags, batting order, team). Nothing
here calls a network, reads evaluation/, or invents a statistic --
"opponent quality" and "team popularity" are both computed from the
SAME slate's own hitter projections, not from Vegas data we don't have.
"""

from typing import Dict, List, Optional

from config.ownership_config import (
    BATTING_ORDER_OWNERSHIP_WEIGHT,
    DEFAULT_BATTING_ORDER_WEIGHT,
    POSITION_SCARCITY_QUALITY_FRACTION,
    POSITION_SCARCITY_SATURATION_COUNT,
    SAMPLE_SIZE_DAMPENING,
    VALUE_NORMALIZATION_CONSTANT,
)
from ownership.models import OwnershipInputPlayer, TeamPopularity
from ownership.slate_normalization import compute_percentiles

# Deterministic tags produced by agents/pitcher_agent.py / agents/batter_agent.py
# that serve as proxies for signals we don't carry a raw sub-score for on
# the saved DK player pool (see dfs/models.py's DFSPlayer -- it keeps
# overall_score/tags/reasons, not every component score).
_PITCHER_K_UPSIDE_TAGS = {"elite_k_upside", "elite_whiffs", "elite_csw"}
_HITTER_POWER_TAGS = {"elite_power", "elite_barrel", "elite_hard_hit", "elite_xwoba", "power_sleeper"}


def _value(player: OwnershipInputPlayer) -> float:
    if player.salary <= 0:
        return 0.0
    return player.projection / player.salary * VALUE_NORMALIZATION_CONSTANT


def sample_size_dampening(player: OwnershipInputPlayer) -> float:
    """Hitters only: a tiny-sample player with an extreme projection
    should not automatically project heavy ownership. Pitchers always
    return 1.0 (season_sample_size on the pool is innings pitched, not a
    remotely comparable "tiny sample" situation for an active MLB starter)."""
    if player.player_type != "hitter":
        return 1.0
    pa = player.season_sample_size
    cfg = SAMPLE_SIZE_DAMPENING
    if pa is None:
        return cfg["min_dampening_factor"]
    if pa >= cfg["season_pa_threshold"]:
        return 1.0
    if pa <= cfg["season_pa_floor"]:
        return cfg["min_dampening_factor"]
    span = cfg["season_pa_threshold"] - cfg["season_pa_floor"]
    progress = (pa - cfg["season_pa_floor"]) / span
    return cfg["min_dampening_factor"] + progress * (1.0 - cfg["min_dampening_factor"])


def _batting_order_weight(batting_order: Optional[int]) -> float:
    if batting_order is None:
        return DEFAULT_BATTING_ORDER_WEIGHT
    return BATTING_ORDER_OWNERSHIP_WEIGHT.get(batting_order, DEFAULT_BATTING_ORDER_WEIGHT)


def _canonical_position(player: OwnershipInputPlayer) -> Optional[str]:
    """First DK-listed position is treated as the player's primary slot
    for scarcity grouping -- prevents double-counting a multi-position
    player's OWN scarcity bonus across two positions at once. Alternative
    *counting* for other players still considers every position a
    multi-position player is genuinely eligible for (see
    _position_alternatives), since that's a real availability fact."""
    return player.dk_positions[0] if player.dk_positions else None


def compute_team_popularity(hitters: List[OwnershipInputPlayer]) -> Dict[str, TeamPopularity]:
    """Aggregate, slate-relative offensive popularity per team. Built
    entirely from this slate's own hitter projections -- NOT a Vegas
    implied-total model (we don't have one)."""
    by_team: Dict[str, List[OwnershipInputPlayer]] = {}
    for h in hitters:
        by_team.setdefault(h.team, []).append(h)

    raw_by_team: Dict[str, float] = {}
    stats: Dict[str, TeamPopularity] = {}
    for team, players in by_team.items():
        projections = sorted((p.projection for p in players), reverse=True)
        aggregate = sum(projections)
        top5 = sum(projections[:5])
        avg_value = sum(_value(p) for p in players) / len(players)
        lineup_completeness = min(1.0, len(players) / 9.0)
        # Simple transparent blend -- not fit to any slate's outcomes.
        raw = (aggregate * 0.4) + (top5 * 0.4) + (avg_value * 0.1 * len(players)) + (lineup_completeness * 20.0)
        raw_by_team[team] = raw
        stats[team] = TeamPopularity(
            team=team, team_popularity_score=0.0, aggregate_projection=round(aggregate, 2),
            top5_projection=round(top5, 2), hitter_count=len(players),
        )

    percentiles = compute_percentiles(list(raw_by_team.items()))
    for team, pct in percentiles.items():
        stats[team].team_popularity_score = round(pct, 2)
    return stats


def _position_alternatives(position: str, hitters: List[OwnershipInputPlayer]) -> List[OwnershipInputPlayer]:
    return [h for h in hitters if position in h.dk_positions]


def _scarcity_score(player: OwnershipInputPlayer, hitters: List[OwnershipInputPlayer]) -> float:
    position = _canonical_position(player)
    if position is None:
        return 50.0
    alternatives = _position_alternatives(position, hitters)
    if not alternatives:
        return 50.0
    best_projection = max(a.projection for a in alternatives)
    if best_projection <= 0:
        return 50.0
    attractive = [a for a in alternatives if a.projection >= best_projection * POSITION_SCARCITY_QUALITY_FRACTION]
    saturation = min(1.0, len(attractive) / POSITION_SCARCITY_SATURATION_COUNT)
    return 100.0 * (1.0 - saturation)


def build_pitcher_features(pitchers: List[OwnershipInputPlayer], team_popularity: Dict[str, TeamPopularity]) -> Dict[str, Dict[str, float]]:
    if not pitchers:
        return {}

    projection_pct = compute_percentiles([(p.dk_player_id, p.projection) for p in pitchers])
    ceiling_pct = compute_percentiles([(p.dk_player_id, p.ceiling) for p in pitchers])
    salary_pct = compute_percentiles([(p.dk_player_id, float(p.salary)) for p in pitchers])
    value_pct = compute_percentiles([(p.dk_player_id, _value(p)) for p in pitchers])
    overall_pct = compute_percentiles([(p.dk_player_id, p.overall_score if p.overall_score is not None else 50.0) for p in pitchers])

    # Opponent weakness: the LOWER the opposing offense's popularity
    # score, the more attractive this pitcher's own matchup looks.
    opponent_quality_pct: Dict[str, float] = {}
    for p in pitchers:
        team_stats = team_popularity.get(p.opponent) if p.opponent else None
        opponent_quality_pct[p.dk_player_id] = 100.0 - (team_stats.team_popularity_score if team_stats else 50.0)

    # Salary savings relative to a comparable-projection peer group.
    savings_raw: Dict[str, float] = {}
    for p in pitchers:
        band = max(p.projection * 0.15, 0.5)
        comparable = [q for q in pitchers if abs(q.projection - p.projection) <= band]
        avg_comparable_salary = sum(q.salary for q in comparable) / len(comparable)
        savings_raw[p.dk_player_id] = avg_comparable_salary - p.salary
    savings_pct = compute_percentiles(list(savings_raw.items()))

    features: Dict[str, Dict[str, float]] = {}
    for p in pitchers:
        pid = p.dk_player_id
        k_upside = 100.0 if _PITCHER_K_UPSIDE_TAGS & set(p.tags) else 45.0
        confidence = p.confidence if p.confidence is not None else 50.0
        features[pid] = {
            "projection_percentile": projection_pct.get(pid, 50.0),
            "ceiling_percentile": ceiling_pct.get(pid, 50.0),
            "salary_percentile": salary_pct.get(pid, 50.0),
            "value_percentile": value_pct.get(pid, 50.0),
            "overall_score_percentile": overall_pct.get(pid, 50.0),
            "k_upside": k_upside,
            "confidence": confidence,
            "opponent_weakness_percentile": opponent_quality_pct.get(pid, 50.0),
            "salary_savings_percentile": savings_pct.get(pid, 50.0),
        }
    return features


def build_hitter_features(hitters: List[OwnershipInputPlayer], team_popularity: Dict[str, TeamPopularity]) -> Dict[str, Dict[str, float]]:
    if not hitters:
        return {}

    projection_pct = compute_percentiles([(h.dk_player_id, h.projection) for h in hitters])
    ceiling_pct = compute_percentiles([(h.dk_player_id, h.ceiling) for h in hitters])
    salary_pct = compute_percentiles([(h.dk_player_id, float(h.salary)) for h in hitters])
    value_pct = compute_percentiles([(h.dk_player_id, _value(h)) for h in hitters])
    overall_pct = compute_percentiles([(h.dk_player_id, h.overall_score if h.overall_score is not None else 50.0) for h in hitters])

    features: Dict[str, Dict[str, float]] = {}
    for h in hitters:
        hid = h.dk_player_id
        team_stats = team_popularity.get(h.team)
        power_signal = min(100.0, 35.0 * len(_HITTER_POWER_TAGS & set(h.tags)))
        confidence = h.confidence if h.confidence is not None else 50.0
        features[hid] = {
            "projection_percentile": projection_pct.get(hid, 50.0),
            "ceiling_percentile": ceiling_pct.get(hid, 50.0),
            "salary_percentile": salary_pct.get(hid, 50.0),
            "value_percentile": value_pct.get(hid, 50.0),
            "overall_score_percentile": overall_pct.get(hid, 50.0),
            "position_scarcity": _scarcity_score(h, hitters),
            "team_popularity": team_stats.team_popularity_score if team_stats else 50.0,
            "batting_order_effect": _batting_order_weight(h.batting_order),
            "power_signal": power_signal,
            "confidence": confidence,
        }
    return features
