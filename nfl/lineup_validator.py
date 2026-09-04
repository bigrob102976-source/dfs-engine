"""NFL M3/M13 -- independent post-hoc lineup validation. The solver's
own constraints are trusted to produce legal output, but this module
re-derives every check from scratch against the raw player pool --
never assumes solver success implies legality (mirrors
optimizer/validator.py's stated philosophy for MLB).

Validates SLOT ASSIGNMENTS, not just aggregate base-position counts: a
lineup containing 3 real RBs is only valid if exactly 2 are assigned to
the RB1/RB2 slots and the third to FLEX -- a lineup with 3 RBs and 0 at
FLEX (e.g. 3 RBs and a missing WR) is invalid even though the aggregate
RB count alone might look sufficient.

NFL M13 adds independent re-checks for QB stacking, bring-back, RB+DST
correlation, team/game limits, and (via validate_lineup_set) exposure
compliance and pairwise uniqueness across a generated batch -- mirrors
optimizer/validator.py's identical split between per-lineup and set-
level checks.
"""

from typing import Dict, Iterable, List, Optional, Set

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS, DK_NFL_CLASSIC_SALARY_CAP, DK_NFL_ROSTER_SIZE
from config.nfl_optimizer_config import BRING_BACK_COUNTS, BRING_BACK_ELIGIBLE_POSITIONS, QB_STACK_PASS_CATCHER_POSITIONS, QB_STACK_RECEIVER_COUNTS
from nfl.optimizer_models import NflLineup, NflOptimizerPlayer, NflStackConfig

_VALID_MODES = frozenset({"roster_feasibility", "projection", "ceiling", "leverage"})

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
    stack: Optional[NflStackConfig] = None,
) -> List[str]:
    """`stack` is optional -- pass the NflStackConfig the lineup was
    built with to independently re-check QB stack/bring-back/RB+DST/
    team/game limits; omit it to validate only roster legality (the
    original NFL M3 scope)."""
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
    # never re-derived from position.
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

    if lineup.mode not in _VALID_MODES:
        violations.append(f"Lineup mode is {lineup.mode!r}, expected one of {sorted(_VALID_MODES)}.")

    if stack is not None:
        violations.extend(_stack_violations(lineup, players_by_key, stack))

    return violations


def _stack_violations(lineup: NflLineup, players_by_key: Dict[str, NflOptimizerPlayer], stack: NflStackConfig) -> List[str]:
    violations: List[str] = []
    assigned = [players_by_key[a.draftkings_player_id] for a in lineup.assignments if a.draftkings_player_id in players_by_key]

    qb = next((p for p in assigned if p.position == "QB"), None)

    if stack.qb_stack_mode != "off":
        min_receivers = QB_STACK_RECEIVER_COUNTS[stack.qb_stack_mode]
        if qb is None:
            violations.append("QB stack required but no QB found in lineup.")
        else:
            catcher_count = sum(1 for p in assigned if p.position in QB_STACK_PASS_CATCHER_POSITIONS and p.team == qb.team)
            if catcher_count < min_receivers:
                violations.append(
                    f"QB stack requirement ({stack.qb_stack_mode}, need {min_receivers} same-team WR/TE) not met: "
                    f"{qb.name} ({qb.team}) has only {catcher_count}."
                )

    if stack.bring_back_mode != "off" and qb is not None:
        bring_back_min = BRING_BACK_COUNTS[stack.bring_back_mode]
        bb_count = sum(1 for p in assigned if p.position in BRING_BACK_ELIGIBLE_POSITIONS and qb.opponent and p.team == qb.opponent)
        if bb_count < bring_back_min:
            violations.append(f"Bring-back requirement not met: no eligible opposing ({qb.opponent}) RB/WR/TE in lineup.")

    if stack.rb_dst_enabled:
        dst = next((p for p in assigned if p.position == "DST"), None)
        if dst is not None:
            has_rb = any(p.position == "RB" and p.team == dst.team for p in assigned)
            if not has_rb:
                violations.append(f"RB+DST requirement not met: {dst.name} ({dst.team}) has no same-team RB in lineup.")

    if stack.max_players_per_team is not None:
        team_counts: Dict[str, int] = {}
        for p in assigned:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1
        for team, count in team_counts.items():
            if count > stack.max_players_per_team:
                violations.append(f"{team}: {count} players exceeds max_players_per_team of {stack.max_players_per_team}.")

    if stack.max_players_per_game is not None:
        game_counts: Dict[str, int] = {}
        for p in assigned:
            game_counts[p.game_id] = game_counts.get(p.game_id, 0) + 1
        for game_id, count in game_counts.items():
            if count > stack.max_players_per_game:
                violations.append(f"Game {game_id}: {count} players exceeds max_players_per_game of {stack.max_players_per_game}.")

    return violations


def validate_lineup_set(
    lineups: List[NflLineup],
    players_by_key: Dict[str, NflOptimizerPlayer],
    salary_cap: int = DK_NFL_CLASSIC_SALARY_CAP,
    locked_keys: Iterable[str] = (),
    excluded_keys: Iterable[str] = (),
    stack: Optional[NflStackConfig] = None,
    max_exposure_caps: Optional[Dict[str, int]] = None,
    min_exposure_targets: Optional[Dict[str, int]] = None,
    min_unique: int = 1,
) -> Dict[int, List[str]]:
    """Per-lineup checks (validate_lineup) plus set-level checks:
    exposure cap/target compliance across the whole batch, and pairwise
    uniqueness. Mirrors optimizer/validator.py::validate_lineup_set()."""
    results: Dict[int, List[str]] = {
        lineup.index: validate_lineup(lineup, players_by_key, salary_cap, locked_keys, excluded_keys, stack)
        for lineup in lineups
    }

    counts: Dict[str, int] = {}
    for lineup in lineups:
        for key in lineup.player_keys():
            counts[key] = counts.get(key, 0) + 1

    if max_exposure_caps:
        for key, cap in max_exposure_caps.items():
            if counts.get(key, 0) > cap:
                name = players_by_key[key].name if key in players_by_key else key
                for lineup in lineups:
                    if key in lineup.player_keys():
                        results.setdefault(lineup.index, []).append(
                            f"Exposure cap exceeded for {name}: appears in {counts[key]} lineups (cap {cap})."
                        )

    if min_exposure_targets:
        for key, target in min_exposure_targets.items():
            actual = counts.get(key, 0)
            if actual < target:
                name = players_by_key[key].name if key in players_by_key else key
                if lineups:
                    results.setdefault(lineups[0].index, []).append(
                        f"Exposure target not met for {name}: appears in {actual} lineup(s), target was {target}."
                    )

    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            shared = set(a.player_keys()) & set(b.player_keys())
            diff = DK_NFL_ROSTER_SIZE - len(shared)
            if diff < min_unique:
                results.setdefault(a.index, []).append(
                    f"Lineup {a.index} and lineup {b.index} differ by only {diff} player(s) (min_unique={min_unique})."
                )

    return results
