"""NFL M3 -- independent post-hoc lineup validation. The solver's own
constraints are trusted to produce legal output, but this module
re-derives every check from scratch against the raw player pool --
never assumes solver success implies legality (mirrors
optimizer/validator.py's stated philosophy for MLB).

Validates SLOT ASSIGNMENTS, not just aggregate base-position counts: a
lineup containing 3 real RBs is only valid if exactly 2 are assigned to
the RB1/RB2 slots and the third to FLEX -- a lineup with 3 RBs and 0 at
FLEX (e.g. 3 RBs and a missing WR) is invalid even though the aggregate
RB count alone might look sufficient.
"""

from typing import Dict, Iterable, List

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS, DK_NFL_CLASSIC_SALARY_CAP, DK_NFL_ROSTER_SIZE
from nfl.optimizer_models import NflLineup, NflOptimizerPlayer

# instance label ("RB1") -> base slot name ("RB") -- the inverse of
# nfl/solver.py::_expand_slot_instances(), needed here so validation
# doesn't depend on importing the solver module.
_INSTANCE_TO_BASE_SLOT: Dict[str, str] = {}
for _slot in DK_NFL_CLASSIC_ROSTER_SLOTS:
    _base = _slot["slot"]
    if _slot["count"] == 1:
        _INSTANCE_TO_BASE_SLOT[_base] = _base
    else:
        for _i in range(1, _slot["count"] + 1):
            _INSTANCE_TO_BASE_SLOT[f"{_base}{_i}"] = _base

_EXPECTED_INSTANCE_COUNTS: Dict[str, int] = {}
for _slot in DK_NFL_CLASSIC_ROSTER_SLOTS:
    _base = _slot["slot"]
    if _slot["count"] == 1:
        _EXPECTED_INSTANCE_COUNTS[_base] = 1
    else:
        for _i in range(1, _slot["count"] + 1):
            _EXPECTED_INSTANCE_COUNTS[f"{_base}{_i}"] = 1


def validate_lineup(
    lineup: NflLineup,
    players_by_key: Dict[str, NflOptimizerPlayer],
    salary_cap: int = DK_NFL_CLASSIC_SALARY_CAP,
    locked_keys: Iterable[str] = (),
    excluded_keys: Iterable[str] = (),
) -> List[str]:
    violations: List[str] = []
    keys = [a.draftkings_player_id for a in lineup.assignments]

    if len(lineup.assignments) != DK_NFL_ROSTER_SIZE:
        violations.append(f"Roster size is {len(lineup.assignments)}, expected {DK_NFL_ROSTER_SIZE}.")

    # Slot-instance counts (RB1, RB2, ... each exactly once) -- catches
    # a solver bug that filled the same instance twice or skipped one,
    # which an aggregate base-position count alone would miss.
    instance_counts: Dict[str, int] = {}
    for a in lineup.assignments:
        instance_counts[a.slot] = instance_counts.get(a.slot, 0) + 1
    for instance_label, expected in _EXPECTED_INSTANCE_COUNTS.items():
        actual = instance_counts.get(instance_label, 0)
        if actual != expected:
            violations.append(f"Slot {instance_label}: {actual} filled, expected {expected}.")
    unexpected_slots = set(instance_counts) - set(_EXPECTED_INSTANCE_COUNTS)
    if unexpected_slots:
        violations.append(f"Unexpected slot label(s) in lineup: {sorted(unexpected_slots)}.")

    # Every assignment's player must be genuinely eligible for the base
    # slot it's assigned to, per the player's own real roster_slots --
    # never re-derived from position. A lineup with 3 RBs is only valid
    # if exactly one of them is assigned to FLEX (checked above via
    # instance counts) AND that RB's roster_slots actually includes "FLEX".
    for a in lineup.assignments:
        base_slot = _INSTANCE_TO_BASE_SLOT.get(a.slot)
        player = players_by_key.get(a.draftkings_player_id)
        if player is None:
            violations.append(f"Slot {a.slot}: player {a.draftkings_player_id!r} not found in the pool.")
            continue
        if base_slot is None:
            continue  # already reported as an unexpected slot label above
        if base_slot not in player.roster_slots:
            violations.append(
                f"Slot {a.slot}: {player.name!r} (roster_slots={player.roster_slots}) is not eligible for {base_slot!r}."
            )

    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        violations.append(f"Duplicate player ID(s) in lineup: {dupes}.")

    if lineup.total_salary > salary_cap:
        violations.append(f"Total salary {lineup.total_salary} exceeds the salary cap {salary_cap}.")
    if lineup.total_salary != sum(a.salary for a in lineup.assignments):
        violations.append("Reported total_salary does not match the sum of assignment salaries.")

    draft_group_ids = {players_by_key[k].draft_group_id for k in keys if k in players_by_key}
    if len(draft_group_ids) > 1 or (draft_group_ids and lineup.draft_group_id not in draft_group_ids):
        violations.append(f"Players originate from inconsistent DraftGroup(s): {sorted(draft_group_ids)} vs lineup.draft_group_id={lineup.draft_group_id}.")

    missing_locks = set(locked_keys) - set(keys)
    if missing_locks:
        violations.append(f"Locked player(s) missing from lineup: {sorted(missing_locks)}.")
    present_excludes = set(excluded_keys) & set(keys)
    if present_excludes:
        violations.append(f"Excluded player(s) present in lineup: {sorted(present_excludes)}.")

    if lineup.mode != "roster_feasibility":
        violations.append(f"Lineup mode is {lineup.mode!r}, expected 'roster_feasibility' for NFL M3.")

    return violations
