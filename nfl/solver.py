"""NFL M3 -- DraftKings Classic NFL roster-feasibility solver.

A small, self-contained CP-SAT formulation reproducing only the generic
slot-assignment CORE of optimizer/solver.py (one binary variable per
concrete roster-slot instance x eligible player, exactly-one-per-slot,
each player used in at most one slot, salary cap, uniqueness across
previously-generated lineups) -- not the full MLB optimizer engine,
which is tightly coupled to non-Optional projection/ceiling fields
(optimizer/objective.py) and pitcher/hitter-specific constraints
(optimizer/constraints.py) that don't apply here and that M3 explicitly
doesn't need yet (no stacking, no ownership, no team-conflict rules).

Slot eligibility always checks a canonical player's own real
`roster_slots` field (nfl/pool_builder.py, derived directly from
DraftKings' own roster_slot_id per player) -- never re-derived from
base position. A player is eligible for the "FLEX" slot if and only if
DraftKings' own data already marked them FLEX-eligible.

M3's objective is a clearly labeled feasibility proof, not a fantasy
recommendation: maximize deterministic salary utilization (no
projection/ceiling exists anywhere in nfl/optimizer_models.py to
optimize instead). Every generated NflLineup carries
mode="roster_feasibility" explicitly.
"""

from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS
from nfl.models import NflPlayer
from nfl.optimizer_models import (
    NflGenerationResult,
    NflLineup,
    NflLineupSlotAssignment,
    NflOptimizerPlayer,
    NflOptimizerSettings,
)

SOLVER_MAX_TIME_SECONDS = 10.0
SOLVER_NUM_SEARCH_WORKERS = 1
SOLVER_RANDOM_SEED = 42


class NflOptimizerConfigError(ValueError):
    """A lock/exclude setting is contradictory or unresolvable. Raised
    BEFORE any solver call -- never silently dropped or ignored."""


def to_optimizer_players(players: List[NflPlayer]) -> List[NflOptimizerPlayer]:
    """Reduces the canonical M2 NflPlayer pool to only what the
    feasibility solver needs. No projection/ownership field is carried
    over -- there's nothing to invent, and the solver never looks for one."""
    return [
        NflOptimizerPlayer(
            key=p.draftkings_player_id, name=p.name, team=p.team, opponent=p.opponent, game_id=p.game_id,
            position=p.position, roster_slots=list(p.roster_slots), salary=p.salary,
            is_team_entity=p.is_team_entity, draft_group_id=p.draft_group_id, slate_date=p.slate_date,
        )
        for p in players
    ]


def _expand_slot_instances() -> List[Tuple[str, str]]:
    """Returns [(instance_label, base_slot_name), ...] -- e.g.
    [("QB","QB"), ("RB1","RB"), ("RB2","RB"), ..., ("FLEX","FLEX"), ("DST","DST")].
    Ordinal labels (RB1/RB2, WR1/WR2/WR3) for output; the base slot name
    is what eligible_for_slot() checks against roster_slots."""
    instances: List[Tuple[str, str]] = []
    for slot in DK_NFL_CLASSIC_ROSTER_SLOTS:
        base = slot["slot"]
        count = slot["count"]
        if count == 1:
            instances.append((base, base))
        else:
            for i in range(1, count + 1):
                instances.append((f"{base}{i}", base))
    return instances


def eligible_for_slot(base_slot: str, players: List[NflOptimizerPlayer]) -> List[NflOptimizerPlayer]:
    return [p for p in players if base_slot in p.roster_slots]


def solve_single_lineup(
    players: List[NflOptimizerPlayer],
    settings: NflOptimizerSettings,
    forced_locks: Set[str] = frozenset(),
    forced_excludes: Set[str] = frozenset(),
    previous_lineups: Optional[List[List[str]]] = None,
) -> Optional[List[Tuple[str, NflOptimizerPlayer]]]:
    """Returns a list of (instance_label, NflOptimizerPlayer) covering
    every roster slot, or None if no legal lineup exists under these
    constraints."""
    previous_lineups = previous_lineups or []
    candidate_pool = [p for p in players if p.key not in forced_excludes]
    by_key = {p.key: p for p in candidate_pool}
    slot_instances = _expand_slot_instances()

    model = cp_model.CpModel()

    x: Dict[Tuple[int, str], "cp_model.IntVar"] = {}
    for slot_index, (_label, base_slot) in enumerate(slot_instances):
        eligible = eligible_for_slot(base_slot, candidate_pool)
        if not eligible:
            return None
        for player in eligible:
            x[(slot_index, player.key)] = model.NewBoolVar(f"x_{slot_index}_{player.key}")

    for slot_index, (_label, base_slot) in enumerate(slot_instances):
        eligible = eligible_for_slot(base_slot, candidate_pool)
        model.Add(sum(x[(slot_index, p.key)] for p in eligible) == 1)

    used: Dict[str, "cp_model.IntVar"] = {}
    for player in candidate_pool:
        var_list = [x[(i, player.key)] for i in range(len(slot_instances)) if (i, player.key) in x]
        if not var_list:
            continue
        u = model.NewBoolVar(f"used_{player.key}")
        model.Add(sum(var_list) == u)
        used[player.key] = u

    for key in forced_locks:
        if key not in used:
            return None
        model.Add(used[key] == 1)

    model.Add(sum(used[k] * by_key[k].salary for k in used) <= settings.salary_cap)

    for prev_keys in previous_lineups:
        prev_vars = [used[k] for k in prev_keys if k in used]
        if len(prev_vars) == len(prev_keys):
            model.Add(sum(prev_vars) <= len(prev_keys) - settings.min_unique)

    # Feasibility objective ONLY: maximize deterministic salary
    # utilization. There is no projection/ceiling field on
    # NflOptimizerPlayer to optimize instead -- this never claims to
    # produce a good fantasy lineup, only a legal one.
    model.Maximize(sum(used[k] * by_key[k].salary for k in used))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = SOLVER_NUM_SEARCH_WORKERS
    solver.parameters.random_seed = SOLVER_RANDOM_SEED
    solver.parameters.max_time_in_seconds = settings.time_limit_seconds if settings.time_limit_seconds is not None else SOLVER_MAX_TIME_SECONDS
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    result: List[Tuple[str, NflOptimizerPlayer]] = []
    for slot_index, (label, base_slot) in enumerate(slot_instances):
        for player in eligible_for_slot(base_slot, candidate_pool):
            if (slot_index, player.key) in x and solver.Value(x[(slot_index, player.key)]) == 1:
                result.append((label, player))
                break
    return result


def generate_lineups(players: List[NflOptimizerPlayer], settings: NflOptimizerSettings) -> NflGenerationResult:
    """Generates up to settings.num_lineups distinct legal lineups.
    Raises NflOptimizerConfigError for a contradictory/unresolvable
    lock or exclude setting BEFORE any solver call -- never silently
    drops a lock. Stops (without raising) and reports stopped_reason
    when the solver itself can't find a legal lineup for the next slot
    (e.g. an impossible combination of locks)."""
    by_key = {p.key: p for p in players}

    locked_keys = set(settings.locks)
    excluded_keys = set(settings.excludes)

    unknown_locks = locked_keys - by_key.keys()
    if unknown_locks:
        raise NflOptimizerConfigError(f"Locked player key(s) not found in pool: {sorted(unknown_locks)}.")
    unknown_excludes = excluded_keys - by_key.keys()
    if unknown_excludes:
        raise NflOptimizerConfigError(f"Excluded player key(s) not found in pool: {sorted(unknown_excludes)}.")

    conflict = locked_keys & excluded_keys
    if conflict:
        names = [by_key[k].name for k in conflict]
        raise NflOptimizerConfigError(f"Player(s) both locked and excluded -- contradiction: {names}")

    if len(locked_keys) > sum(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS):
        raise NflOptimizerConfigError(
            f"{len(locked_keys)} players locked, but a DraftKings Classic NFL lineup only has "
            f"{sum(s['count'] for s in DK_NFL_CLASSIC_ROSTER_SLOTS)} roster spots."
        )

    lineups: List[NflLineup] = []
    previous_keys_list: List[List[str]] = []
    stopped_reason: Optional[str] = None

    for i in range(settings.num_lineups):
        result = solve_single_lineup(players, settings, forced_locks=locked_keys, forced_excludes=excluded_keys, previous_lineups=previous_keys_list)
        if result is None:
            stopped_reason = f"No legal lineup found for lineup #{i + 1} (locks/excludes/uniqueness/salary cap together are unsatisfiable)."
            break

        assignments = [
            NflLineupSlotAssignment(slot=slot, draftkings_player_id=p.key, name=p.name, position=p.position, team=p.team, salary=p.salary)
            for slot, p in result
        ]
        total_salary = sum(a.salary for a in assignments)
        first_player = result[0][1]
        lineups.append(NflLineup(
            index=i, assignments=assignments, total_salary=total_salary,
            remaining_salary=settings.salary_cap - total_salary,
            draft_group_id=first_player.draft_group_id, slate_date=first_player.slate_date,
        ))
        previous_keys_list.append([p.key for _, p in result])

    return NflGenerationResult(lineups=lineups, requested=settings.num_lineups, generated=len(lineups), stopped_reason=stopped_reason)
