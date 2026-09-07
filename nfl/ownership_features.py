"""NFL M12 -- percentile-based ownership features, computed relative to
one DraftGroup's own player pool (mirrors ownership/features.py's and
ownership/slate_normalization.py's "always slate-relative, never a
fixed/global threshold" discipline).

Every percentile helper here delegates its actual ranking math to
ownership/slate_normalization.py's compute_percentiles() -- that
function is 100% sport-agnostic (operates on Dict[str, float] pairs,
no MLB concepts anywhere in it), so it's imported directly rather than
reimplemented (see NFL M12 Phase 0's audit: this is the one MLB module
safe to reuse byte-for-byte).

A feature whose real input is missing (no ceiling, no usage data, no
Vegas) resolves to a neutral 50.0 percentile rather than being
omitted -- that's the same "no signal, assume average" convention
ownership/model.py's own single-player-slate fallback already uses.
Neutral 50.0 contributes ZERO differentiating signal to the weighted
score (every player who lacks the input gets the identical value), so
this never fabricates a preference -- it just means that feature adds
no information for that player, exactly as if it were absent."""

from typing import Dict, List

from config.nfl_ownership_config import VALUE_NORMALIZATION_CONSTANT
from nfl.ownership_models import NflOwnershipInputPlayer
from ownership.slate_normalization import compute_percentiles

NEUTRAL_PERCENTILE = 50.0


def _percentile_or_neutral(pairs: List[tuple]) -> Dict[str, float]:
    """pairs: [(id, value_or_None), ...]. Players with a real value are
    percentile-ranked against EACH OTHER ONLY; players with None get the
    neutral fallback directly (never included in the ranking pool, since
    a missing value has no real rank)."""
    real_pairs = [(pid, v) for pid, v in pairs if v is not None]
    missing_ids = [pid for pid, v in pairs if v is None]
    pct = compute_percentiles(real_pairs)
    for pid in missing_ids:
        pct[pid] = NEUTRAL_PERCENTILE
    return pct


def build_position_features(players: List[NflOwnershipInputPlayer]) -> Dict[str, Dict[str, float]]:
    """Percentile features computed WITHIN one position's own pool
    (players should all share the same `.position` -- the caller groups
    by position before calling this, see nfl/ownership_model.py). Every
    returned feature is a 0-100 percentile."""
    if not players:
        return {}

    salary_pct = _percentile_or_neutral([(p.draftkings_player_id, float(p.salary)) for p in players])
    projection_pct = _percentile_or_neutral([(p.draftkings_player_id, p.projection) for p in players])
    ceiling_pct = _percentile_or_neutral([(p.draftkings_player_id, p.ceiling) for p in players])
    usage_pct = _percentile_or_neutral([(p.draftkings_player_id, p.usage_share) for p in players])
    team_total_pct = _percentile_or_neutral([(p.draftkings_player_id, p.team_implied_total) for p in players])

    value_pairs = []
    for p in players:
        value = (p.projection / p.salary * VALUE_NORMALIZATION_CONSTANT) if p.salary else None
        value_pairs.append((p.draftkings_player_id, value))
    value_pct = _percentile_or_neutral(value_pairs)

    # DST-only: LOW opponent implied total is the attractive matchup, so
    # rank ascending (best matchup = highest percentile) by ranking on
    # the NEGATED value -- compute_percentiles() itself only ever ranks
    # ascending-value-to-ascending-percentile, so negating is the
    # correct, transparent way to invert desirability without a special
    # "descending" mode in a function every other feature here also
    # relies on behaving identically.
    opponent_weakness_pairs = []
    for p in players:
        opp_total = p.opponent_implied_total
        opponent_weakness_pairs.append((p.draftkings_player_id, (-opp_total) if opp_total is not None else None))
    opponent_weakness_pct = _percentile_or_neutral(opponent_weakness_pairs)

    features: Dict[str, Dict[str, float]] = {}
    for p in players:
        pid = p.draftkings_player_id
        features[pid] = {
            "salary_percentile": salary_pct[pid],
            "projection_percentile": projection_pct[pid],
            "ceiling_percentile": ceiling_pct[pid],
            "value_percentile": value_pct[pid],
            "usage_percentile": usage_pct[pid],
            "team_total_percentile": team_total_pct[pid],
            "opponent_weakness_percentile": opponent_weakness_pct[pid],
        }
    return features


def build_combined_flex_features(flex_players: List[NflOwnershipInputPlayer]) -> Dict[str, float]:
    """FLEX-worthiness score computed ACROSS the combined RB+WR+TE pool
    (not within each player's own position) -- FLEX competition is
    cross-position, so an RB's flex-worthiness must be directly
    comparable to a WR's or TE's, which a within-position percentile
    cannot provide. Blends the same two signals as the base
    per-position score (projection + value), each computed on the
    combined pool, weighted evenly -- see
    nfl/ownership_model.py::_allocate_flex_ownership() for how this
    feeds the shared FLEX allocation. Returns a single 0-100 score per
    player, already averaged (not a dict of sub-features -- there's
    nothing downstream that needs the sub-components separately)."""
    if not flex_players:
        return {}

    projection_pct = _percentile_or_neutral([(p.draftkings_player_id, p.projection) for p in flex_players])
    value_pairs = []
    for p in flex_players:
        value = (p.projection / p.salary * VALUE_NORMALIZATION_CONSTANT) if p.salary else None
        value_pairs.append((p.draftkings_player_id, value))
    value_pct = _percentile_or_neutral(value_pairs)

    return {
        p.draftkings_player_id: (projection_pct[p.draftkings_player_id] + value_pct[p.draftkings_player_id]) / 2.0
        for p in flex_players
    }
