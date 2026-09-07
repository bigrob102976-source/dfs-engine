"""NFL M6B Phase 4 -- position compatibility between DraftKings' base
position (QB/RB/WR/TE -- DST is handled entirely separately, never
through this module) and nflverse's real roster `position` value.

Audited live (M6B Phase 1/4) against real DraftGroup 151307 x real
nflreadpy.load_rosters(seasons=2026): of 695 real offensive DK players,
642 had an exact, unique normalized-name+team match in nflverse -- and
in every one of those 642 real cases, nflverse's `position` was
IDENTICAL to DraftKings' declared position. The ~14 name+team matches
whose nflverse position DIFFERED (e.g. nflverse position "LS"/"DB"/"KR"/
"TE" against a DK-declared "RB"/"WR"/"TE") were investigated and are
real DIFFERENT people who happen to share both a name and a team
abbreviation with the intended player -- not the same player recorded
under two position tags. Exact equality is therefore the only
compatibility rule this module defines; nothing broader (e.g. treating
FB as RB-compatible) is added speculatively, because no real observed
same-player case has ever required it. If one is found later, add it
here with the same live-audit discipline.

FLEX is explicitly NEVER a value either side of this comparison can
take: FLEX is DraftKings roster-slot eligibility only (nfl/models.py's
own NflPlayer.position is documented as "never FLEX"), not a base
position -- this module operates purely on true base positions."""

from typing import Optional

DK_OFFENSIVE_BASE_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


def is_position_compatible(dk_position: str, candidate_position: Optional[str]) -> bool:
    if dk_position not in DK_OFFENSIVE_BASE_POSITIONS:
        raise ValueError(f"is_position_compatible is for offensive base positions only, got {dk_position!r} (DST is handled separately; FLEX is never a base position).")
    if not candidate_position:
        return False
    return candidate_position.strip().upper() == dk_position
