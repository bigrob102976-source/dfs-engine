"""NFL M4 -- merges NflProjectionRecord list into the M2 canonical
NflPlayer pool, and validates the merged result.

Player matching: DraftKings player_id (NflPlayer.draftkings_player_id
== NflProjectionRecord.canonical_player_id) is the ONLY matching
strategy for M4 -- it's real, stable, and unambiguous (see NFL M2's own
investigation: every DK draftable, including DST, carries this exact
identity). No name+team+position fallback is implemented: NFL M2 has no
crosswalk or research package yet to make a name-based match safely
disambiguated, and a silent fuzzy match risks attaching a projection to
the WRONG player -- worse than reporting it unmatched. A future name-
based fallback (for a provider that doesn't supply DK IDs) can be added
later without breaking this module's contract.

DST identity: unambiguous under this strategy -- confirmed in M2, each
team's defense has its own stable, real DraftKings player_id, exactly
like a person.
"""

from typing import Dict, List

from nfl.models import NflPlayer
from nfl.projection_models import (
    NFL_PROJECTION_POSITIONS,
    NflProjectionRecord,
    NflProjectionValidationFinding,
    NflProjectionValidationResult,
)


class NflProjectionMergeResult:
    """Output of merge_projections(): which pool players got a real
    projection attached, plus an honest account of what didn't match --
    never silently dropped."""

    def __init__(self, projections_by_player_id: Dict[str, NflProjectionRecord], matched: List[str], unmatched_records: List[str], unmatched_pool: List[str]):
        self.projections_by_player_id = projections_by_player_id
        self.matched = matched  # canonical_player_ids successfully matched
        self.unmatched_records = unmatched_records  # projection record player_ids with no matching pool player
        self.unmatched_pool = unmatched_pool  # pool player_ids with no projection record


def merge_projections(pool: List[NflPlayer], records: List[NflProjectionRecord]) -> NflProjectionMergeResult:
    pool_by_id = {p.draftkings_player_id: p for p in pool}
    pool_ids = set(pool_by_id)

    projections_by_player_id: Dict[str, NflProjectionRecord] = {}
    matched: List[str] = []
    unmatched_records: List[str] = []

    for record in records:
        if record.canonical_player_id in pool_by_id:
            projections_by_player_id[record.canonical_player_id] = record
            matched.append(record.canonical_player_id)
        else:
            unmatched_records.append(record.canonical_player_id)

    unmatched_pool = sorted(pool_ids - set(matched))

    return NflProjectionMergeResult(
        projections_by_player_id=projections_by_player_id,
        matched=matched,
        unmatched_records=unmatched_records,
        unmatched_pool=unmatched_pool,
    )


def validate_projections(
    pool: List[NflPlayer], records: List[NflProjectionRecord], draft_group_id: int, expected_provenance: str,
) -> NflProjectionValidationResult:
    findings: List[NflProjectionValidationFinding] = []
    pool_by_id = {p.draftkings_player_id: p for p in pool}

    seen_keys = set()
    for record in records:
        if record.projection is not None:
            if isinstance(record.projection, bool) or not isinstance(record.projection, (int, float)):
                findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: projection is not numeric ({record.projection!r})."))
            else:
                value = float(record.projection)
                if value != value:  # NaN check -- NaN is the only float that isn't equal to itself
                    findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: projection is NaN."))
                elif value in (float("inf"), float("-inf")):
                    findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: projection is infinite."))
                elif value < 0:
                    findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: negative projection ({value}) is not supported/justified for NFL M4."))

        key = (record.canonical_player_id, record.source, record.model_version)
        if key in seen_keys:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: duplicate projection for the same player/source/version."))
        seen_keys.add(key)

        pool_player = pool_by_id.get(record.canonical_player_id)
        if pool_player is None:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r} (id={record.canonical_player_id}) is not in the current canonical pool."))
        else:
            if record.position != pool_player.position:
                findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: projection position {record.position!r} != pool position {pool_player.position!r}."))
            if record.team and pool_player.team and record.team != pool_player.team:
                findings.append(NflProjectionValidationFinding("WARN", f"{record.name!r}: projection team {record.team!r} != pool team {pool_player.team!r}."))

        if record.draft_group_id != draft_group_id:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: projection draft_group_id {record.draft_group_id} != expected {draft_group_id}."))
        if not record.source_provenance:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: missing source_provenance."))
        elif record.source_provenance != expected_provenance:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: source_provenance {record.source_provenance!r} != expected {expected_provenance!r}."))
        if not record.generated_at:
            findings.append(NflProjectionValidationFinding("WARN", f"{record.name!r}: missing generated_at timestamp."))

        if record.position not in NFL_PROJECTION_POSITIONS:
            findings.append(NflProjectionValidationFinding("BLOCK", f"{record.name!r}: unsupported position {record.position!r}."))

    merge = merge_projections(pool, records)
    projected_ids = set(merge.matched)
    total = len(pool)
    projected = len(projected_ids)
    position_counts: Dict[str, int] = {}
    for pid in projected_ids:
        pos = pool_by_id[pid].position
        position_counts[pos] = position_counts.get(pos, 0) + 1

    return NflProjectionValidationResult(
        passed=not any(f.level == "BLOCK" for f in findings),
        findings=findings,
        total_pool_players=total,
        projected_players=projected,
        missing_players=total - projected,
        match_rate=(projected / total) if total else None,
        position_projected_counts=position_counts,
    )
