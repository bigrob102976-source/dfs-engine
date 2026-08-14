"""Matches an external provider's projections to our own independent
(Big Money) player identities, and builds the merged PlayerProjectionRecord
for each match. This module ONLY does identity matching + copying values
across -- it never computes an adjustment (see adjustment_engine.py) and
never mutates either side's original values.

Matching mirrors dfs/player_resolver.py's tiered approach but simplified
for this purpose (no DK-specific crosswalk/position concepts): exact
normalized (name, team) match first, falling back to a name-only match
ONLY if it is unique across the independent player list. Ambiguous or
unmatched players are reported, never silently guessed.
"""

from typing import Dict, List, Tuple

from dfs.name_normalization import normalize_name
from external_projections.models import (
    ExternalProjectionPlayer,
    PlayerProjectionRecord,
    ProjectionMergeResult,
)


def _index_independent(records: List[dict]) -> Tuple[Dict[Tuple[str, str], List[dict]], Dict[str, List[dict]]]:
    by_name_team: Dict[Tuple[str, str], List[dict]] = {}
    by_name: Dict[str, List[dict]] = {}
    for r in records:
        key_name = normalize_name(r["name"])
        by_name_team.setdefault((key_name, r["team"]), []).append(r)
        by_name.setdefault(key_name, []).append(r)
    return by_name_team, by_name


def match_external_to_independent(
    external_players: List[ExternalProjectionPlayer], independent_records: List[dict], player_type: str,
) -> ProjectionMergeResult:
    """`independent_records` are raw pitcher_board["pitchers"] or
    batter_board["hitters"] snapshot records (dicts, as persisted).
    `player_type` is "pitcher" | "hitter", recorded on every output
    record so a pitcher-pass and hitter-pass merge can be combined."""
    by_name_team, by_name = _index_independent(independent_records)

    records: List[PlayerProjectionRecord] = []
    unmatched_external: List[str] = []
    ambiguous_external: List[str] = []
    matched_independent_ids = set()

    for ext in external_players:
        key_name = normalize_name(ext.name)
        candidates = by_name_team.get((key_name, ext.team), [])
        if len(candidates) == 1:
            match = candidates[0]
        elif len(candidates) > 1:
            ambiguous_external.append(ext.name)
            continue
        else:
            name_candidates = by_name.get(key_name, [])
            if len(name_candidates) == 1:
                match = name_candidates[0]
            elif len(name_candidates) > 1:
                ambiguous_external.append(ext.name)
                continue
            else:
                unmatched_external.append(ext.name)
                continue

        matched_independent_ids.add(match["player_id"])
        records.append(PlayerProjectionRecord(
            independent_player_id=str(match["player_id"]),
            name=match["name"],
            team=match["team"],
            player_type=player_type,
            external_player_id=ext.external_player_id,
            external_projection=ext.projection,
            external_ceiling=ext.ceiling,
            external_floor=ext.floor,
            external_provider=ext.provider_name,
            external_provider_timestamp=ext.updated_at,
            independent_projection=match.get("projection"),
            independent_ceiling=match.get("ceiling"),
            independent_floor=match.get("floor"),
        ))

    unmatched_independent = [r["name"] for r in independent_records if str(r["player_id"]) not in matched_independent_ids]

    return ProjectionMergeResult(
        records=records, unmatched_external=unmatched_external,
        unmatched_independent=unmatched_independent, ambiguous_external=ambiguous_external,
    )
