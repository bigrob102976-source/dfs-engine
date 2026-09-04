"""NFL M12 -- merges NflOwnershipRecord list into the M2 canonical
NflPlayer pool. Mirrors nfl/projection_merge.py exactly: DraftKings
player_id (NflPlayer.draftkings_player_id == NflOwnershipRecord.
canonical_player_id) is the ONLY matching strategy -- never a name
fallback (see nfl/projection_merge.py's own docstring for why a silent
fuzzy match is worse than reporting a player unmatched)."""

from typing import Dict, List

from nfl.models import NflPlayer
from nfl.ownership_models import NflOwnershipRecord


class NflOwnershipMergeResult:
    def __init__(self, ownership_by_player_id: Dict[str, NflOwnershipRecord], matched: List[str], unmatched_records: List[str], unmatched_pool: List[str]):
        self.ownership_by_player_id = ownership_by_player_id
        self.matched = matched  # canonical_player_ids successfully matched
        self.unmatched_records = unmatched_records  # ownership record player_ids with no matching pool player
        self.unmatched_pool = unmatched_pool  # pool player_ids with no ownership record (e.g. no usable projection)


def merge_ownership(pool: List[NflPlayer], records: List[NflOwnershipRecord]) -> NflOwnershipMergeResult:
    pool_by_id = {p.draftkings_player_id: p for p in pool}
    pool_ids = set(pool_by_id)

    ownership_by_player_id: Dict[str, NflOwnershipRecord] = {}
    matched: List[str] = []
    unmatched_records: List[str] = []

    for record in records:
        if record.canonical_player_id in pool_by_id:
            ownership_by_player_id[record.canonical_player_id] = record
            matched.append(record.canonical_player_id)
        else:
            unmatched_records.append(record.canonical_player_id)

    unmatched_pool = sorted(pool_ids - set(matched))

    return NflOwnershipMergeResult(
        ownership_by_player_id=ownership_by_player_id,
        matched=matched,
        unmatched_records=unmatched_records,
        unmatched_pool=unmatched_pool,
    )
