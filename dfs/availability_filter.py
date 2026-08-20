"""Milestone 31.1: DraftKings Status/AvgPointsPerGame availability
filtering -- a layer on top of dfs/eligibility.py's confirmed-starter
classification, not a replacement for it.

dfs/eligibility.py answers "is this player in today's confirmed
starting lineup." This module answers a different question: even for a
confirmed starter, does DraftKings' OWN data say they shouldn't be
trusted for this slate -- specifically an "IL" status (DraftKings has
flagged them injured) or a demonstrated AvgPointsPerGame of exactly
0.0 (no recent production to speak of). "DTD" (day-to-day) is
deliberately only FLAGGED, never excluded -- day-to-day players
frequently do play, and excluding them outright would silently narrow
the pool on a guess this module has no basis for.

Every DK row is preserved -- see dfs/player_pool.py's "never silently
drop" discipline, which this module extends rather than breaks. This
pass only ever narrows `optimizer_eligible` (AND-combined with
dfs/eligibility.py's own determination) and appends a "DTD" tag; it
never removes a row from the pool and never changes eligibility_status.

Each rule is independently toggleable via this module's own function
parameters -- callers that want only one rule active can pass the other
as False rather than needing a second code path.
"""

from dataclasses import dataclass, field
from typing import List

from dfs.models import DFSPlayer

STATUS_IL = "IL"
STATUS_DTD = "DTD"
DTD_TAG = "DTD"

REASON_STATUS_IL = "DK Status = IL"
REASON_ZERO_AVG_POINTS = "AvgPointsPerGame = 0.0"


@dataclass
class ExclusionRecord:
    dk_player_id: str
    name: str
    team: str
    reason: str

    def to_dict(self) -> dict:
        return {"dk_player_id": self.dk_player_id, "name": self.name, "team": self.team, "reason": self.reason}


@dataclass
class AvailabilityFilterResult:
    excluded: List[ExclusionRecord] = field(default_factory=list)
    kept_count: int = 0
    dropped_count: int = 0

    def to_dict(self) -> dict:
        return {"excluded": [e.to_dict() for e in self.excluded], "kept_count": self.kept_count, "dropped_count": self.dropped_count}


def apply_availability_filters(
    players: List[DFSPlayer],
    exclude_il: bool = True,
    exclude_zero_avg_points: bool = True,
) -> AvailabilityFilterResult:
    """Mutates `players` in place: narrows `optimizer_eligible` for any
    row this pass excludes, and appends a "DTD" tag for any DTD row
    (flagged, never excluded). Evaluated against EVERY row regardless of
    player_type/eligibility_status, matching what DraftKings' own Status
    column describes about that specific row -- an IL pitcher and an IL
    bench hitter are both real exclusions worth logging, even though the
    bench hitter was already ineligible for an unrelated reason.

    Returns a result whose `kept_count`/`dropped_count` are measured
    against the full `players` list (every preserved DK row), not just
    the subset dfs/eligibility.py already considered eligible -- this is
    what "269 raw rows -> ~211 kept" is counting."""
    excluded: List[ExclusionRecord] = []

    for player in players:
        if player.dk_status == STATUS_DTD and DTD_TAG not in player.tags:
            player.tags.append(DTD_TAG)

        reason = None
        if exclude_il and player.dk_status == STATUS_IL:
            reason = REASON_STATUS_IL
        elif exclude_zero_avg_points and player.avg_points_per_game_dk == 0.0:
            reason = REASON_ZERO_AVG_POINTS

        if reason is not None:
            player.optimizer_eligible = False
            excluded.append(ExclusionRecord(dk_player_id=player.dk_player_id, name=player.name, team=player.team, reason=reason))

    dropped_count = len(excluded)
    return AvailabilityFilterResult(excluded=excluded, kept_count=len(players) - dropped_count, dropped_count=dropped_count)
