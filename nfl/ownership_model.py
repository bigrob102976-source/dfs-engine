"""NFL M12 -- Big Money Native NFL ownership estimator (nfl_ownership_v1).

DETERMINISTIC, not trained ML: no real historical DraftKings NFL
ownership data exists anywhere in this repo (Phase 4 audit), so there
is nothing to supervise a model against. This is an honest, hand-set,
transparent estimator -- see config/nfl_ownership_config.py's module
docstring for why its weights aren't "fit" to anything, and revisit
this whole module (not just its config numbers) once real historical
NFL ownership becomes available and a genuinely trained model is worth
building.

The one problem MLB's ownership/model.py never had to solve: NFL
Classic's roster has a single shared FLEX slot spanning RB/WR/TE
(config/dk_roster_config_nfl.py), so those three positions' ownership
pools cannot be normalized independently the way MLB's clean pitcher/
hitter split allows. See _allocate_flex_ownership() below for the
documented algorithm (also explained in
config/nfl_ownership_config.py::FLEX_CONCENTRATION_EXPONENT).

Every raw feature-to-score step reuses ownership/slate_normalization.py's
generic, sport-agnostic compute_percentiles()/normalize_with_cap() --
the one MLB module Phase 0's audit found safe to reuse byte-for-byte
(pure Dict[str, float] math, zero MLB concepts). Nothing else from
ownership/ is imported: ownership/model.py, ownership/features.py, and
ownership/leverage.py are all directly coupled to MLB's pitcher/hitter
split and config/ownership_config.py's MLB-tuned thresholds (Phase 0
audit), so this module reimplements the small amount of leverage/
quality/confidence math it needs using NFL's own config instead."""

from typing import Dict, List, Optional

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS, FLEX_ELIGIBLE_BASE_POSITIONS
from config.nfl_ownership_config import (
    BASE_CONCENTRATION_EXPONENT,
    CHALK_OWNERSHIP_THRESHOLD,
    FLEX_CONCENTRATION_EXPONENT,
    LEVERAGE_TAG_THRESHOLDS,
    MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE,
    NFL_OWNERSHIP_METHOD,
    NFL_OWNERSHIP_MODEL_VERSION,
    NFL_OWNERSHIP_SOURCE,
    OWNERSHIP_CONFIDENCE_WEIGHTS,
    OWNERSHIP_TIER_THRESHOLDS,
    POSITION_OWNERSHIP_WEIGHTS,
    SLATE_SIZE_FULL_CONFIDENCE_PLAYER_COUNT,
    VALUE_NORMALIZATION_CONSTANT,
)
from nfl.ownership_features import build_combined_flex_features, build_position_features
from nfl.ownership_models import (
    NFL_OWNERSHIP_POSITIONS,
    NflOwnershipInputPlayer,
    NflOwnershipRecord,
)
from ownership.slate_normalization import compute_percentiles, normalize_with_cap

BASE_SLOT_COUNTS: Dict[str, int] = {s["slot"]: s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS if s["slot"] != "FLEX"}
FLEX_SLOT_COUNT = next(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS if s["slot"] == "FLEX")


def _usage_share_for_player(position: str, rolling: Optional[Dict[str, Optional[float]]], season_to_date: Optional[Dict[str, Optional[float]]]) -> Optional[float]:
    """Blends the position-relevant usage share(s) from whichever real
    window is available (rolling last-3 preferred, season-to-date as
    fallback) -- never fabricates a share the underlying usage records
    don't support. QB/DST have no usage-share concept (their real
    signal is production/matchup, not a target/carry share), so this
    always returns None for them."""
    def pick(field: str) -> Optional[float]:
        for source in (rolling, season_to_date):
            if not source:
                continue
            for suffix in ("_mean_last3", "_season_mean", "_mean_last5", "_mean_last1"):
                value = source.get(f"{field}{suffix}")
                if value is not None:
                    return value
        return None

    if position == "RB":
        parts = [v for v in (pick("carry_share"), pick("target_share")) if v is not None]
    elif position in ("WR", "TE"):
        parts = [v for v in (pick("target_share"), pick("reception_share")) if v is not None]
    else:
        return None
    return (sum(parts) / len(parts)) if parts else None


def _weighted_score(feature_values: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(feature_values[name] * weight for name, weight in weights.items())


def _ownership_tier(pct: float) -> str:
    for name, low, high in OWNERSHIP_TIER_THRESHOLDS:
        if low <= pct < high:
            return name
    return OWNERSHIP_TIER_THRESHOLDS[-1][0]


def _quality_percentile(f: Dict[str, float]) -> float:
    return (f["projection_percentile"] + f["ceiling_percentile"]) / 2.0


def _leverage_score(quality_pct: float, ownership_pct: float) -> float:
    return quality_pct - ownership_pct


def _assign_tags(leverage: float, ownership: float, ceiling_pct: float, quality_pct: float, tier: str) -> List[str]:
    t = LEVERAGE_TAG_THRESHOLDS
    tags: List[str] = []
    if leverage >= t["elite_leverage"]:
        tags.append("elite_leverage")
    elif leverage >= t["positive_leverage"]:
        tags.append("positive_leverage")
    elif leverage <= t["negative_leverage"]:
        tags.append("negative_leverage")

    chalk_tiers = ("high", "very_high") if t["chalk_min_ownership_tier"] == "high" else ("very_high",)
    if tier in chalk_tiers:
        tags.append("chalk")

    if ownership <= t["low_owned_ceiling_max_ownership"] and ceiling_pct >= t["low_owned_ceiling_min_ceiling_percentile"]:
        tags.append("low_owned_ceiling")
    if ownership <= t["contrarian_max_ownership"] and quality_pct >= t["contrarian_min_quality_percentile"]:
        tags.append("contrarian")
    return tags


def _ownership_confidence(pool_size: int, position_pool_size: int, has_ceiling: bool, has_usage_or_vegas: bool) -> float:
    w = OWNERSHIP_CONFIDENCE_WEIGHTS
    slate_size_factor = min(1.0, pool_size / SLATE_SIZE_FULL_CONFIDENCE_PLAYER_COUNT) * 100.0
    position_pool_factor = min(1.0, position_pool_size / MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE) * 100.0
    input_completeness = 100.0 if (has_ceiling and has_usage_or_vegas) else (60.0 if has_ceiling else 30.0)
    raw = (
        w["slate_size_factor"] * slate_size_factor
        + w["position_pool_factor"] * position_pool_factor
        + w["input_completeness_factor"] * input_completeness
    )
    return round(min(100.0, max(0.0, raw)), 2)


def _reasons(position: str, f: Dict[str, float], tier: str) -> List[str]:
    reasons: List[str] = []
    if f["projection_percentile"] >= 80:
        reasons.append(f"Ranks in the top tier of {position}s in projection on this slate.")
    if f["value_percentile"] >= 80:
        reasons.append("Strong salary-adjusted value relative to the rest of the slate.")
    if position in ("RB", "WR", "TE") and f["usage_percentile"] >= 75:
        reasons.append("High recent opportunity share (targets/carries) relative to the rest of the slate.")
    if position == "QB" and f["team_total_percentile"] >= 75:
        reasons.append("Favorable Vegas implied team total.")
    if position == "DST" and f["opponent_weakness_percentile"] >= 75:
        reasons.append("Favorable matchup against a weaker opposing offense.")
    if f["salary_percentile"] >= 80 and f["ceiling_percentile"] >= 70 and f["projection_percentile"] < 60:
        reasons.append("Strong ceiling but expensive salary may limit projected field exposure.")
    if not reasons:
        if tier in ("very_low", "low"):
            reasons.append("Modest projection and value relative to the rest of the slate keep projected ownership low.")
        else:
            reasons.append("Middle-of-the-pack projection and value relative to the rest of the slate.")
    return reasons[:6]


def _normalize_with_per_player_cap(raw_scores: Dict[str, float], target_sum: float, caps: Dict[str, float], max_iterations: int = 25) -> Dict[str, float]:
    """Same capped-waterfall algorithm as ownership/slate_normalization.py's
    normalize_with_cap() (that function's docstring explains the
    mechanics in full), generalized to a PER-PLAYER cap instead of one
    shared scalar. Reimplemented locally rather than extending the
    shared MLB module (NFL M12 stays fully isolated from ownership/*.py
    -- see this file's top docstring). Needed so a strong RB/WR/TE's
    FLEX share can never push their TOTAL (base + flex) ownership over
    100% -- solving that with post-hoc clipping would silently DESTROY
    ownership mass, breaking the "RB+WR+TE+FLEX == 700%" invariant
    (NFL M12 Phase 2/7) instead of truly respecting it."""
    if not raw_scores:
        return {}
    remaining_ids = set(raw_scores.keys())
    result: Dict[str, float] = {}
    remaining_target = target_sum

    for _ in range(max_iterations):
        total_raw = sum(max(0.0, raw_scores[i]) for i in remaining_ids)
        if total_raw <= 0:
            share = remaining_target / len(remaining_ids) if remaining_ids else 0.0
            for i in remaining_ids:
                result[i] = min(caps.get(i, 0.0), max(0.0, share))
            remaining_ids = set()
            break

        scaled = {i: max(0.0, raw_scores[i]) / total_raw * remaining_target for i in remaining_ids}
        overflow_ids = {i for i, v in scaled.items() if v > caps.get(i, 0.0)}
        if not overflow_ids:
            result.update(scaled)
            remaining_ids = set()
            break

        for i in overflow_ids:
            cap_i = max(0.0, caps.get(i, 0.0))
            result[i] = cap_i
            remaining_target -= cap_i
        remaining_ids -= overflow_ids
        if not remaining_ids:
            break

    if remaining_ids:
        share = remaining_target / len(remaining_ids)
        for i in remaining_ids:
            result[i] = min(caps.get(i, 0.0), max(0.0, share))

    return {i: max(0.0, v) for i, v in result.items()}


def _allocate_flex_ownership(rb_wr_te_players: List[NflOwnershipInputPlayer], base_ownership: Dict[str, float]) -> Dict[str, float]:
    """NFL M12 Phase 7 -- the shared FLEX slot's 100% (FLEX_SLOT_COUNT *
    100) of ownership mass, allocated across the COMBINED RB+WR+TE pool
    using each player's cross-position flex-worthiness score (see
    nfl/ownership_features.py::build_combined_flex_features()), raised
    to FLEX_CONCENTRATION_EXPONENT before proportional redistribution --
    see config/nfl_ownership_config.py's docstring for why.

    Each player's flex share is capped at (100 - their own base
    ownership), not a flat 100 -- this is what guarantees base+flex
    never exceeds 100% for any individual player WITHOUT resorting to
    post-hoc clipping (see _normalize_with_per_player_cap()'s
    docstring). Returns {draftkings_player_id: flex_ownership_share},
    only for players actually in rb_wr_te_players (never QB/DST --
    FLEX_ELIGIBLE_BASE_POSITIONS excludes them by DraftKings' own real
    eligibility, see config/dk_roster_config_nfl.py)."""
    combined_scores = build_combined_flex_features(rb_wr_te_players)
    raw_flex_scores = {pid: score ** FLEX_CONCENTRATION_EXPONENT for pid, score in combined_scores.items()}
    caps = {pid: 100.0 - base_ownership.get(pid, 0.0) for pid in raw_flex_scores}
    return _normalize_with_per_player_cap(raw_flex_scores, target_sum=FLEX_SLOT_COUNT * 100.0, caps=caps)


def build_nfl_ownership_projections(
    players: List[NflOwnershipInputPlayer],
    draft_group_id: int,
    slate_date: str,
    source_provenance: str,
    generated_at: str,
) -> "tuple[List[NflOwnershipRecord], dict]":
    """`players` must already be filtered to ONLY players with a real,
    usable projection (see this module's top docstring -- a player with
    no projection has nothing for this estimator to work from, and must
    never enter this function; the caller is responsible for giving
    such a player ownership_projection = None directly, without calling
    this at all for them). Returns (records, normalization_report)."""
    by_position: Dict[str, List[NflOwnershipInputPlayer]] = {pos: [] for pos in NFL_OWNERSHIP_POSITIONS}
    for p in players:
        by_position.setdefault(p.position, []).append(p)

    features_by_position: Dict[str, Dict[str, Dict[str, float]]] = {
        pos: build_position_features(pos_players) for pos, pos_players in by_position.items()
    }

    raw_scores_by_position: Dict[str, Dict[str, float]] = {}
    for pos, pos_players in by_position.items():
        weights = POSITION_OWNERSHIP_WEIGHTS[pos]
        raw_scores_by_position[pos] = {
            # Concentration exponent (config/nfl_ownership_config.py's
            # docstring has the full rationale): a raw percentile-blend
            # score is applied here BEFORE normalize_with_cap, not after,
            # since normalize_with_cap's proportional split is what
            # actually turns a wide/narrow raw-score spread into a wide/
            # narrow ownership spread.
            p.draftkings_player_id: _weighted_score(features_by_position[pos][p.draftkings_player_id], weights) ** BASE_CONCENTRATION_EXPONENT
            for p in pos_players
        }

    # Base (guaranteed-slot) ownership per position -- QB/DST get their
    # full slot mass here (they're never FLEX-eligible); RB/WR/TE get
    # ONLY their guaranteed-slot mass (2/3/1 * 100), with the shared
    # FLEX slot's mass allocated separately below.
    base_ownership: Dict[str, float] = {}
    for pos, pos_players in by_position.items():
        if not pos_players:
            continue
        target_sum = BASE_SLOT_COUNTS[pos] * 100.0
        base_ownership.update(normalize_with_cap(raw_scores_by_position[pos], target_sum=target_sum))

    flex_pool = [p for p in players if p.position in FLEX_ELIGIBLE_BASE_POSITIONS]
    flex_ownership = _allocate_flex_ownership(flex_pool, base_ownership)

    # _allocate_flex_ownership()'s per-player cap already guarantees
    # base+flex <= 100 for every player -- this loop's min(100.0, ...)/
    # overflow tracking is a defensive, independently-verifiable safety
    # net (floating-point slack across the waterfall's iterations, never
    # a real source of ownership mass loss the way a flat 100 cap was).
    total_ownership: Dict[str, float] = {}
    flex_component: Dict[str, float] = {}
    clipped_overflow_total = 0.0
    clipped_player_count = 0
    for p in players:
        base = base_ownership.get(p.draftkings_player_id, 0.0)
        flex = flex_ownership.get(p.draftkings_player_id, 0.0)
        combined = base + flex
        capped = min(100.0, combined)
        if combined > 100.0 + 1e-6:
            clipped_overflow_total += combined - 100.0
            clipped_player_count += 1
        total_ownership[p.draftkings_player_id] = round(capped, 2)
        flex_component[p.draftkings_player_id] = round(flex, 2)

    ownership_pct_by_position: Dict[str, Dict[str, float]] = {}
    for pos, pos_players in by_position.items():
        if not pos_players:
            continue
        pairs = [(p.draftkings_player_id, total_ownership[p.draftkings_player_id]) for p in pos_players]
        ownership_pct_by_position[pos] = compute_percentiles(pairs)

    pool_size = len(players)
    records: List[NflOwnershipRecord] = []
    for pos, pos_players in by_position.items():
        if not pos_players:
            continue
        for p in pos_players:
            pid = p.draftkings_player_id
            f = features_by_position[pos][pid]
            owned = total_ownership[pid]
            own_pct = ownership_pct_by_position[pos][pid]
            quality_pct = _quality_percentile(f)
            leverage = round(_leverage_score(quality_pct, own_pct), 2)
            tier = _ownership_tier(owned)
            tags = _assign_tags(leverage, owned, f["ceiling_percentile"], quality_pct, tier)
            chalk = round(_weighted_score(
                {"ownership_percentile": own_pct, "projection_percentile": f["projection_percentile"], "value_percentile": f["value_percentile"]},
                {"ownership_percentile": 0.5, "projection_percentile": 0.3, "value_percentile": 0.2},
            ), 2)
            confidence = _ownership_confidence(
                pool_size, len(pos_players), has_ceiling=p.ceiling is not None,
                has_usage_or_vegas=(p.usage_share is not None or p.team_implied_total is not None or p.opponent_implied_total is not None),
            )
            value = round(p.projection / p.salary * VALUE_NORMALIZATION_CONSTANT, 3) if p.salary else None

            records.append(NflOwnershipRecord(
                sport="NFL", draft_group_id=draft_group_id, slate_date=slate_date,
                draftkings_player_id=pid, canonical_player_id=pid, name=p.name, position=pos,
                team=p.team, opponent=p.opponent,
                ownership_projection=owned, ownership_rank=None,  # rank filled in below, once every record exists
                source=NFL_OWNERSHIP_SOURCE, source_provenance=source_provenance,
                method=NFL_OWNERSHIP_METHOD, model_version=NFL_OWNERSHIP_MODEL_VERSION, generated_at=generated_at,
                salary=p.salary, projection=p.projection, ceiling=p.ceiling, value=value,
                ownership_tier=tier, chalk_score=chalk, leverage_score=leverage, ownership_confidence=confidence,
                flex_ownership_component=(flex_component[pid] if pos in FLEX_ELIGIBLE_BASE_POSITIONS else None),
                feature_breakdown=dict(f), tags=tags, reasons=_reasons(pos, f, tier),
            ))

    records.sort(key=lambda r: r.ownership_projection, reverse=True)
    for i, r in enumerate(records):
        r.ownership_rank = i + 1

    normalization_report = _build_normalization_report(by_position, total_ownership, clipped_player_count, clipped_overflow_total)
    return records, normalization_report


def _build_normalization_report(
    by_position: Dict[str, List[NflOwnershipInputPlayer]],
    total_ownership: Dict[str, float],
    clipped_player_count: int,
    clipped_overflow_total: float,
) -> dict:
    sum_by_position: Dict[str, float] = {}
    expected_by_position: Dict[str, float] = {}
    for pos in NFL_OWNERSHIP_POSITIONS:
        pos_players = by_position.get(pos, [])
        sum_by_position[pos] = round(sum(total_ownership[p.draftkings_player_id] for p in pos_players), 2)
        base_expected = BASE_SLOT_COUNTS[pos] * 100.0
        expected_by_position[pos] = base_expected  # informational only for RB/WR/TE -- their TRUE expected total also includes a FLEX share, see flex_expected_total below

    flex_expected_total = FLEX_SLOT_COUNT * 100.0
    total_expected_mass = sum(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS) * 100.0
    total_actual_mass = round(sum(sum_by_position.values()), 2)

    return {
        "ownership_sum_by_position": sum_by_position,
        "ownership_base_expected_by_position": expected_by_position,
        "flex_slot_expected_total": flex_expected_total,
        "flex_eligible_positions": sorted(FLEX_ELIGIBLE_BASE_POSITIONS),
        "total_expected_mass": total_expected_mass,
        "total_actual_mass": total_actual_mass,
        "players_clipped_at_100": clipped_player_count,
        "ownership_mass_lost_to_clipping": round(clipped_overflow_total, 2),
    }
