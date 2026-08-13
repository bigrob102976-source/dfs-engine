"""Single-lineup CP-SAT solver.

Formulated as a roster-slot assignment problem: 10 concrete roster-slot
instances (P, P, C, 1B, 2B, 3B, SS, OF, OF, OF), one binary variable per
(slot instance, eligible player) pair, each slot filled by exactly one
player, each player used in at most one slot. This is what lets a
multi-position player (e.g. eligible ["1B", "OF"]) legally fill either
slot while still only ever occupying exactly one.

Deterministic by construction: single search worker, fixed random seed
(config/optimizer_config.py) -- the same player pool and settings always
produce the same lineup.
"""

from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS
from config.optimizer_config import SOLVER_MAX_TIME_SECONDS, SOLVER_NUM_SEARCH_WORKERS, SOLVER_RANDOM_SEED
from optimizer.constraints import hitters_by_team, pitcher_vs_hitter_conflicts
from optimizer.models import OptimizerPlayer, OptimizerSettings
from optimizer.objective import scaled_objective_value

# Integer scale for the optional max-total-ownership constraint (CP-SAT
# needs integer coefficients); mirrors optimizer/objective.py's OBJECTIVE_SCALE pattern.
OWNERSHIP_SCALE = 100


def expand_slot_instances() -> List[str]:
    instances: List[str] = []
    for slot in DK_CLASSIC_ROSTER_SLOTS:
        instances.extend([slot["slot"]] * slot["count"])
    return instances


def eligible_for_slot(slot: str, players: List[OptimizerPlayer]) -> List[OptimizerPlayer]:
    if slot == "P":
        return [p for p in players if p.player_type == "pitcher"]
    return [p for p in players if p.player_type == "hitter" and slot in p.dk_positions]


def solve_single_lineup(
    players: List[OptimizerPlayer],
    settings: OptimizerSettings,
    forced_locks: Set[str] = frozenset(),
    forced_excludes: Set[str] = frozenset(),
    previous_lineups: Optional[List[List[str]]] = None,
) -> Optional[List[Tuple[str, OptimizerPlayer]]]:
    """Returns a list of (slot_label, OptimizerPlayer) covering every
    roster slot, or None if no legal lineup exists under these constraints."""
    previous_lineups = previous_lineups or []
    candidate_pool = [p for p in players if p.key not in forced_excludes]
    by_key = {p.key: p for p in candidate_pool}
    slot_instances = expand_slot_instances()

    model = cp_model.CpModel()

    x: Dict[Tuple[int, str], "cp_model.IntVar"] = {}
    for slot_index, slot in enumerate(slot_instances):
        eligible = eligible_for_slot(slot, candidate_pool)
        if not eligible:
            return None
        for player in eligible:
            x[(slot_index, player.key)] = model.NewBoolVar(f"x_{slot_index}_{player.key}")

    for slot_index, slot in enumerate(slot_instances):
        eligible = eligible_for_slot(slot, candidate_pool)
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

    if settings.max_total_ownership is not None:
        # A simple field-exposure constraint on the SUM of individual
        # projected_ownership percentages -- not a duplication/probability
        # model (see ownership/__init__.py and the milestone's explicit
        # warning against overclaiming what this represents). Players with
        # no ownership data (ownership file not loaded, or absent from it)
        # contribute 0 and are not constrained by this at all.
        ownership_terms = [
            used[k] * round(by_key[k].projected_ownership * OWNERSHIP_SCALE)
            for k in used if by_key[k].projected_ownership is not None
        ]
        if ownership_terms:
            model.Add(sum(ownership_terms) <= round(settings.max_total_ownership * OWNERSHIP_SCALE))

    for team, team_hitters in hitters_by_team(candidate_pool).items():
        team_vars = [used[p.key] for p in team_hitters if p.key in used]
        if team_vars:
            model.Add(sum(team_vars) <= settings.team_max_hitters)

    if not settings.allow_pitcher_vs_hitter:
        for pitcher_key, hitter_keys in pitcher_vs_hitter_conflicts(candidate_pool).items():
            if pitcher_key not in used:
                continue
            for hitter_key in hitter_keys:
                if hitter_key in used:
                    model.Add(used[pitcher_key] + used[hitter_key] <= 1)

    if settings.stack_size:
        team_groups = hitters_by_team(candidate_pool)
        if settings.stack_team:
            team_vars = [used[p.key] for p in team_groups.get(settings.stack_team, []) if p.key in used]
            if not team_vars:
                return None
            model.Add(sum(team_vars) >= settings.stack_size)
        else:
            indicators = []
            for team, team_hitters in team_groups.items():
                team_vars = [used[p.key] for p in team_hitters if p.key in used]
                if len(team_vars) < settings.stack_size:
                    continue
                indicator = model.NewBoolVar(f"stack_{team}")
                model.Add(sum(team_vars) >= settings.stack_size).OnlyEnforceIf(indicator)
                model.Add(sum(team_vars) < settings.stack_size).OnlyEnforceIf(indicator.Not())
                indicators.append(indicator)
            if not indicators:
                return None
            model.Add(sum(indicators) >= 1)

    for prev_keys in previous_lineups:
        prev_vars = [used[k] for k in prev_keys if k in used]
        if len(prev_vars) == len(prev_keys):
            model.Add(sum(prev_vars) <= len(prev_keys) - settings.min_unique)

    objective_terms = [used[k] * scaled_objective_value(by_key[k], settings.objective_mode) for k in used]
    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = SOLVER_NUM_SEARCH_WORKERS
    solver.parameters.random_seed = SOLVER_RANDOM_SEED
    solver.parameters.max_time_in_seconds = SOLVER_MAX_TIME_SECONDS
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    result: List[Tuple[str, OptimizerPlayer]] = []
    for slot_index, slot in enumerate(slot_instances):
        for player in eligible_for_slot(slot, candidate_pool):
            if (slot_index, player.key) in x and solver.Value(x[(slot_index, player.key)]) == 1:
                result.append((slot, player))
                break
    return result
