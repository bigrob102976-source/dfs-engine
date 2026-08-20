"""Durable provider-ID -> canonical-identity mapping for DraftKings
unofficial draftables.

MLB reuses dfs/player_resolver.py's exact tiered matching (crosswalk ->
exact name+team -> unique name-only fallback, never guessing on a
collision) against this project's existing research package --
mirrors fantasypros/matcher.py's identical "adapt into a DKSalaryRow,
call resolve_all" pattern rather than building a second bespoke
matcher.

Every OTHER sport reports every draftable as "unmatched": this project
has no canonical player-identity system for NFL/NBA/NHL/etc. yet (only
MLB's research/ package exists) -- reporting honest "unmatched" here is
correct per this milestone's "ambiguous matches must remain
unresolved... never silently attach the wrong player," and is
preferable to inventing a cross-sport identity system this milestone
doesn't ask for. When a non-MLB canonical identity system exists in a
future milestone, this module is the one place that needs to grow a
new branch.
"""

from typing import List, Optional

from dfs.models import DKSalaryRow
from dfs.player_resolver import resolve_all
from draftkings_unofficial.models import DkDraftable, PlayerIdentityMatch

MLB_SPORT_CODE = "MLB"


def _to_dk_row(d: DkDraftable) -> DKSalaryRow:
    position = d.position or ""
    dk_positions = [position] if position else []
    return DKSalaryRow(
        dk_player_id=str(d.draftable_id), name=d.display_name, team_abbrev=d.team_abbreviation or "",
        dk_positions=dk_positions, salary=d.salary or 0, game_info="",
    )


def match_draftables(draftables: List[DkDraftable], sport_code: str, research_package: Optional[dict] = None) -> List[PlayerIdentityMatch]:
    """Returns one PlayerIdentityMatch per input draftable, same order.
    `research_package` is only used (and only meaningful) for MLB --
    see module docstring; ignored for every other sport_code."""
    if not draftables:
        return []

    if sport_code != MLB_SPORT_CODE or research_package is None:
        return [
            PlayerIdentityMatch(
                draftable_id=d.draftable_id, provider_player_id=d.player_id, display_name=d.display_name,
                sport_code=sport_code, match_status="unmatched", match_confidence=None,
            )
            for d in draftables
        ]

    dk_rows = [_to_dk_row(d) for d in draftables]
    matches = resolve_all(dk_rows, research_package)

    results: List[PlayerIdentityMatch] = []
    for draftable, match in zip(draftables, matches):
        results.append(PlayerIdentityMatch(
            draftable_id=draftable.draftable_id, provider_player_id=draftable.player_id,
            display_name=draftable.display_name, sport_code=sport_code, match_status=match.match_status,
            canonical_player_id=match.mlb_player_id, match_confidence=match.match_confidence,
            candidate_ids=list(match.candidate_mlb_ids),
        ))
    return results


def identity_match_summary(matches: List[PlayerIdentityMatch]) -> dict:
    total = len(matches)
    matched = sum(1 for m in matches if m.match_status == "matched")
    unmatched = sum(1 for m in matches if m.match_status == "unmatched")
    ambiguous = sum(1 for m in matches if m.match_status == "ambiguous")
    return {
        "total": total, "matched": matched, "unmatched": unmatched, "ambiguous": ambiguous,
        "match_percent": round(100.0 * matched / total, 1) if total else 0.0,
    }
