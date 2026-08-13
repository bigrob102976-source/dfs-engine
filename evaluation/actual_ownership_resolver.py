"""Resolves raw actual-ownership rows (name, sometimes a DK ID) to the
canonical player identity already established in a pregame ownership
prediction snapshot.

Matching hierarchy (first tier that produces a confident, unique result wins):

1. Exact DK player ID (when the results file happens to carry one).
2. An explicit DK<->MLB crosswalk, if supplied.
3. Conservative normalized player name, unique within the snapshot's
   player pool. Actual DraftKings ownership exports commonly carry
   neither a DK player ID nor a team column, so this is the primary
   real-world path -- reuses dfs.name_normalization (a pure utility;
   evaluation/ depending on pregame utility code is fine, the reverse
   is what's forbidden -- see tests/test_architecture_separation.py).
4. Unmatched -- never guessed.

If more than one snapshot player shares a normalized name, the row is
"ambiguous" and NOT resolved.
"""

from typing import Dict, List, Optional

from dfs.name_normalization import normalize_name
from evaluation.actual_ownership_models import ActualOwnershipRecord, ContestMetadata
from evaluation.actual_ownership_parser import RawActualOwnershipRow


def _build_name_index(snapshot_players: List[dict]) -> Dict[str, List[dict]]:
    index: Dict[str, List[dict]] = {}
    for p in snapshot_players:
        index.setdefault(normalize_name(p["name"]), []).append(p)
    return index


def resolve_actual_ownership(
    raw_rows: List[RawActualOwnershipRow], snapshot_players: List[dict], contest: ContestMetadata,
    source_file: str, crosswalk: Optional[Dict[str, str]] = None,
) -> List[ActualOwnershipRecord]:
    crosswalk = crosswalk or {}
    by_dk_id = {p["dk_player_id"]: p for p in snapshot_players}
    by_mlb_id = {p["mlb_player_id"]: p for p in snapshot_players if p.get("mlb_player_id")}
    name_index = _build_name_index(snapshot_players)

    records: List[ActualOwnershipRecord] = []
    for row in raw_rows:
        snapshot_player = None
        match_status = "unmatched"
        match_confidence = None

        if row.dk_player_id and row.dk_player_id in by_dk_id:
            snapshot_player = by_dk_id[row.dk_player_id]
            match_status, match_confidence = "matched", "exact_dk_id"
        elif row.dk_player_id and row.dk_player_id in crosswalk:
            mlb_id = crosswalk[row.dk_player_id]
            snapshot_player = by_mlb_id.get(mlb_id)
            if snapshot_player:
                match_status, match_confidence = "matched", "crosswalk"

        if snapshot_player is None:
            candidates = name_index.get(normalize_name(row.name), [])
            if len(candidates) == 1:
                snapshot_player = candidates[0]
                match_status, match_confidence = "matched", "name_unique_in_snapshot"
            elif len(candidates) > 1:
                match_status, match_confidence = "ambiguous", None

        records.append(ActualOwnershipRecord(
            dk_player_id=snapshot_player["dk_player_id"] if snapshot_player else row.dk_player_id,
            mlb_player_id=snapshot_player.get("mlb_player_id") if snapshot_player else None,
            name=row.name,
            team=snapshot_player.get("team") if snapshot_player else None,
            player_type=snapshot_player.get("player_type") if snapshot_player else None,
            actual_ownership=row.actual_ownership,
            contest_id=contest.contest_id,
            contest_name=contest.contest_name,
            contest_size=contest.entries,
            source_file=source_file,
            match_status=match_status,
            match_confidence=match_confidence,
        ))
    return records
