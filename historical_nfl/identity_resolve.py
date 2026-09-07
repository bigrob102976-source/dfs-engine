"""NFL M6B -- top-level orchestration tying identity_matching.py's
per-player resolver to a real DK pool (nfl/models.py::NflPlayer list)
and a real nflverse roster snapshot, plus the Phase 9/10 reporting
helpers."""

from typing import Dict, List

from historical_nfl.identity_matching import build_crosswalk_row, build_dst_crosswalk_row, build_roster_indices, resolve_identity
from historical_nfl.identity_models import STATUS_AMBIGUOUS, STATUS_MATCHED, STATUS_REVIEW_REQUIRED, STATUS_UNMATCHED, NflCrosswalkRow, NflIdentityMatchResult
from historical_nfl.identity_position import DK_OFFENSIVE_BASE_POSITIONS


def resolve_offense_pool(
    dk_players: list, existing_crosswalk: Dict[str, NflCrosswalkRow], nflverse_roster_rows: List[dict],
) -> List[NflIdentityMatchResult]:
    """`dk_players` -- nfl.models.NflPlayer instances (DST rows are
    skipped here; see resolve_dst_pool). Returns one NflIdentityMatchResult
    per offensive player, same order as input."""
    by_name_team, by_name = build_roster_indices(nflverse_roster_rows)
    results = []
    for p in dk_players:
        if p.position not in DK_OFFENSIVE_BASE_POSITIONS:
            continue
        results.append(resolve_identity(
            p.draftkings_player_id, p.draftable_ids[0] if p.draftable_ids else None, p.name, p.team, p.position,
            existing_crosswalk, by_name_team, by_name,
        ))
    return results


def resolve_dst_pool(dk_players: list, existing_crosswalk: Dict[str, NflCrosswalkRow]) -> List[NflCrosswalkRow]:
    """DST rows never go through name/GSIS matching (Phase 4) -- team
    abbreviation IS the stable identity."""
    return [
        build_dst_crosswalk_row(p.draftkings_player_id, p.name, p.team, existing=existing_crosswalk.get(p.draftkings_player_id))
        for p in dk_players if p.position == "DST"
    ]


def build_offense_crosswalk_rows(results: List[NflIdentityMatchResult], existing_crosswalk: Dict[str, NflCrosswalkRow]) -> List[NflCrosswalkRow]:
    return [build_crosswalk_row(r, existing_crosswalk.get(r.draftkings_player_id)) for r in results]


def summarize_by_position(results: List[NflIdentityMatchResult], dk_players_by_id: Dict[str, object]) -> Dict[str, dict]:
    """Position -> {total, matched, unmatched, ambiguous, review_required, match_rate}."""
    summary: Dict[str, dict] = {}
    for r in results:
        pos = r.dk_position
        bucket = summary.setdefault(pos, {"total": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "review_required": 0})
        bucket["total"] += 1
        if r.status == STATUS_MATCHED:
            bucket["matched"] += 1
        elif r.status == STATUS_UNMATCHED:
            bucket["unmatched"] += 1
        elif r.status == STATUS_AMBIGUOUS:
            bucket["ambiguous"] += 1
        elif r.status == STATUS_REVIEW_REQUIRED:
            bucket["review_required"] += 1
    for bucket in summary.values():
        bucket["match_rate"] = round(100.0 * bucket["matched"] / bucket["total"], 1) if bucket["total"] else 0.0
    return summary


def classify_history_availability(results: List[NflIdentityMatchResult], historical_gsis_ids: set) -> Dict[str, int]:
    """Phase 10 -- for MATCHED results only, splits by whether the
    resolved gsis_id has any row in a given historical dataset (e.g.
    2025 weekly_player_stats' player_id set). A rookie/new signee with a
    real, matched identity but no historical row yet is NOT an identity
    failure -- this is reported as its own state, separate from
    identity_found_with_history."""
    found_with_history = 0
    found_no_history = 0
    for r in results:
        if r.status != STATUS_MATCHED:
            continue
        if r.gsis_id in historical_gsis_ids:
            found_with_history += 1
        else:
            found_no_history += 1
    return {"identity_found_with_history": found_with_history, "identity_found_no_history": found_no_history}
