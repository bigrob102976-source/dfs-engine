"""NFL M3/M4/M13 -- DraftKings Classic NFL solver: roster-feasibility
mode (M3), projection/ceiling/leverage scoring modes (M4/M13), and NFL
M13's tournament lineup-construction controls (QB stacking, bring-back,
RB+DST correlation, team/game limits, and player exposure across a
multi-lineup batch).

A small, self-contained CP-SAT formulation reproducing only the generic
slot-assignment CORE of optimizer/solver.py (one binary variable per
concrete roster-slot instance x eligible player, exactly-one-per-slot,
each player used in at most one slot, salary cap, uniqueness across
previously-generated lineups) -- not the full MLB optimizer engine,
which is tightly coupled to non-Optional projection/ceiling fields and
pitcher/hitter-specific constraints that don't apply here. NFL M13's
additions mirror MLB's proven patterns (team-stack CP-SAT reification,
deadline-forcing exposure) where the underlying math is sport-agnostic,
and are newly designed where NFL's shape genuinely differs -- see
nfl/constraints.py's module docstring and NFL M13 Phase 0's audit for
exactly which is which.

Slot eligibility always checks a canonical player's own real
`roster_slots` field (nfl/pool_builder.py, derived directly from
DraftKings' own roster_slot_id per player) -- never re-derived from
base position. A player is eligible for the "FLEX" slot if and only if
DraftKings' own data already marked them FLEX-eligible.

Four objective modes, set via NflOptimizerSettings.mode:
  - "roster_feasibility" (M3): maximize deterministic salary
    utilization -- a legality proof, never a fantasy recommendation.
  - "projection" (M4): maximize the sum of REAL Big Money Native
    projections only.
  - "ceiling"/"leverage" (M13): see nfl/objective.py for the exact
    per-mode scoring formula.
Every scoring mode (projection/ceiling/leverage) EXCLUDES a player
missing the real data that mode needs from the candidate pool entirely
-- never silently treated as a 0 (nfl/objective.py::player_is_eligible_
for_mode()). If real-data coverage can't fill every roster slot,
generate_lineups() raises NflProjectionCoverageError BEFORE ever calling
the solver, rather than returning an empty or partial result. No
scoring mode ever falls back to salary, FantasyPros, BlueCollar, or any
synthetic value.
"""

from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS
from config.nfl_optimizer_config import (
    BRING_BACK_COUNTS,
    BRING_BACK_ELIGIBLE_POSITIONS,
    NFL_SCORING_OBJECTIVE_MODES,
    QB_STACK_PASS_CATCHER_POSITIONS,
    QB_STACK_RECEIVER_COUNTS,
)
from nfl.constraints import (
    NflOptimizerConfigError,
    bring_back_candidates_by_team,
    compute_exposure_count_caps,
    compute_min_exposure_targets,
    explain_infeasibility,
    group_by_game,
    group_by_team,
    pass_catchers_by_team,
    rbs_by_team,
    resolve_nfl_settings,
)
from nfl.models import NflPlayer
from nfl.objective import player_is_eligible_for_mode, scaled_objective_value
from nfl.optimizer_models import (
    NflGenerationResult,
    NflLineup,
    NflLineupSlotAssignment,
    NflOptimizerPlayer,
    NflOptimizerSettings,
    NflStackConfig,
)

SOLVER_MAX_TIME_SECONDS = 10.0
# NFL UI M1 -- real finding: a single search worker genuinely cannot
# solve a real, full DK Classic pool (744 real players, confirmed
# against real DraftGroup 151307) within the 10s (or even 30s) time
# limit -- CP-SAT returns UNKNOWN, which solve_single_lineup() then
# treats identically to a genuine INFEASIBLE, silently reporting "no
# legal lineup found" for a real, easily-solvable slate. 8 workers
# solves the real 744-player pool in ~0.35s (confirmed live) -- NFL M13
# keeps this unchanged; every new constraint here is still cheap enough
# that 8 workers comfortably covers real-pool + stacking scenarios (see
# NFL M13 Phase 22's own performance measurement).
SOLVER_NUM_SEARCH_WORKERS = 8
SOLVER_RANDOM_SEED = 42

VALID_MODES = frozenset({"roster_feasibility"}) | frozenset(NFL_SCORING_OBJECTIVE_MODES)


class NflProjectionCoverageError(RuntimeError):
    """Raised in a scoring mode (projection/ceiling/leverage) when real
    (non-None) Big Money Native data doesn't cover enough eligible
    players to fill every roster slot for that mode's requirements.
    Raised BEFORE any solver call -- a scoring mode never silently
    returns an empty result or falls back to salary utilization when
    this happens."""


def to_optimizer_players(players: List[NflPlayer]) -> List[NflOptimizerPlayer]:
    """Reduces the canonical M2 NflPlayer pool to only what the solver
    needs. `projection`/`projected_ownership` are carried over exactly
    as-is (None stays None -- never coerced to 0.0); see
    nfl/projection_merge.py and nfl/ownership_merge.py for how a real
    NflPlayer.projection/ownership get populated. NflPlayer itself
    carries no ceiling/leverage_score field (those live only on
    NflProjectionRecord/NflOwnershipRecord) -- a caller needing
    ceiling-/leverage-mode data should build NflOptimizerPlayer directly
    from those records instead (see scripts/nfl_dashboard_optimize.py)."""
    return [
        NflOptimizerPlayer(
            key=p.draftkings_player_id, name=p.name, team=p.team, opponent=p.opponent, game_id=p.game_id,
            position=p.position, roster_slots=list(p.roster_slots), salary=p.salary,
            is_team_entity=p.is_team_entity, draft_group_id=p.draft_group_id, slate_date=p.slate_date,
            projection=p.projection, projected_ownership=p.ownership,
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


def _add_stack_constraints(
    model: "cp_model.CpModel", used: Dict[str, "cp_model.IntVar"], candidate_pool: List[NflOptimizerPlayer], stack: NflStackConfig,
) -> None:
    """NFL M13 -- QB stack, bring-back, RB+DST, and team/game limits.
    Every rule here is conditioned on WHICH player the solver actually
    selects (via OnlyEnforceIf on that player's own `used` bool var),
    not on a free-standing "some team" choice the way MLB's stack does
    -- NFL has exactly one QB/DST roster slot, so the correlation target
    team is always the ACTUAL rostered QB's/DST's team, never an
    independent decision (see nfl/constraints.py's module docstring)."""
    if stack.qb_stack_mode != "off":
        min_receivers = QB_STACK_RECEIVER_COUNTS[stack.qb_stack_mode]
        catchers_by_team = pass_catchers_by_team(candidate_pool)
        bring_back_min = BRING_BACK_COUNTS[stack.bring_back_mode]
        bring_back_pool = bring_back_candidates_by_team(candidate_pool) if stack.bring_back_mode != "off" else {}

        for qb in [p for p in candidate_pool if p.position == "QB" and p.key in used]:
            catcher_vars = [used[p.key] for p in catchers_by_team.get(qb.team, []) if p.key in used]
            if len(catcher_vars) < min_receivers:
                # This QB structurally cannot satisfy the requested
                # stack with the current candidate pool -- prune rather
                # than let the solver discover it the hard way.
                model.Add(used[qb.key] == 0)
                continue
            model.Add(sum(catcher_vars) >= min_receivers).OnlyEnforceIf(used[qb.key])

            if stack.bring_back_mode != "off":
                bb_vars = [used[p.key] for p in bring_back_pool.get(qb.opponent or "", []) if p.key in used]
                if len(bb_vars) < bring_back_min:
                    model.Add(used[qb.key] == 0)
                    continue
                model.Add(sum(bb_vars) >= bring_back_min).OnlyEnforceIf(used[qb.key])

    if stack.rb_dst_enabled:
        rb_teams = rbs_by_team(candidate_pool)
        for dst in [p for p in candidate_pool if p.position == "DST" and p.key in used]:
            rb_vars = [used[p.key] for p in rb_teams.get(dst.team, []) if p.key in used]
            if not rb_vars:
                model.Add(used[dst.key] == 0)
                continue
            model.Add(sum(rb_vars) >= 1).OnlyEnforceIf(used[dst.key])

    if stack.max_players_per_team is not None:
        for _team, team_players in group_by_team(candidate_pool).items():
            team_vars = [used[p.key] for p in team_players if p.key in used]
            if team_vars:
                model.Add(sum(team_vars) <= stack.max_players_per_team)

    if stack.max_players_per_game is not None:
        for _game_id, game_players in group_by_game(candidate_pool).items():
            game_vars = [used[p.key] for p in game_players if p.key in used]
            if game_vars:
                model.Add(sum(game_vars) <= stack.max_players_per_game)


def solve_single_lineup(
    players: List[NflOptimizerPlayer],
    settings: NflOptimizerSettings,
    forced_locks: Set[str] = frozenset(),
    forced_excludes: Set[str] = frozenset(),
    previous_lineups: Optional[List[List[str]]] = None,
    forced_slot_assignments: Optional[Dict[str, str]] = None,
) -> Optional[List[Tuple[str, NflOptimizerPlayer]]]:
    """Returns a list of (instance_label, NflOptimizerPlayer) covering
    every roster slot, or None if no legal lineup exists under these
    constraints.

    `forced_slot_assignments` (NFL M14 late swap, see nfl/late_swap.py):
    {slot_instance_label: player_key}, pinning a SPECIFIC player to a
    SPECIFIC roster slot instance (e.g. "FLEX" -> "12345"), not just
    "used somewhere" the way forced_locks does -- late swap needs this
    because a locked player's exact DK roster column (e.g. FLEX vs WR1)
    must be preserved for upload consistency (Phase 6), which a plain
    player-level lock can't guarantee. Reuses the SAME `x` slot-
    assignment variables the rest of this function already builds --
    not a second model or a different solver.

    A player named in forced_locks or forced_slot_assignments is never
    excluded from the candidate pool by the current objective mode's
    data-eligibility filter (player_is_eligible_for_mode) -- a locked
    player must remain in the lineup regardless of whether they have a
    fresh projection/ceiling right now (NFL M14 Phase 6: a locked
    player can never be excluded or replaced)."""
    previous_lineups = previous_lineups or []
    forced_slot_assignments = forced_slot_assignments or {}
    always_included_keys = set(forced_locks) | set(forced_slot_assignments.values())

    candidate_pool = [p for p in players if p.key not in forced_excludes]
    candidate_pool = [
        p for p in candidate_pool
        if player_is_eligible_for_mode(p, settings.mode) or p.key in always_included_keys
    ]
    by_key = {p.key: p for p in candidate_pool}
    slot_instances = _expand_slot_instances()
    label_to_slot_index = {label: i for i, (label, _base) in enumerate(slot_instances)}

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

    for slot_label, player_key in forced_slot_assignments.items():
        slot_index = label_to_slot_index.get(slot_label)
        if slot_index is None or (slot_index, player_key) not in x:
            return None  # the slot label is invalid, or this player isn't eligible for it -- can't satisfy
        model.Add(x[(slot_index, player_key)] == 1)

    for key in forced_locks:
        if key not in used:
            return None
        model.Add(used[key] == 1)

    model.Add(sum(used[k] * by_key[k].salary for k in used) <= settings.salary_cap)

    _add_stack_constraints(model, used, candidate_pool, settings.stack)

    for prev_keys in previous_lineups:
        prev_vars = [used[k] for k in prev_keys if k in used]
        if len(prev_vars) == len(prev_keys):
            model.Add(sum(prev_vars) <= len(prev_keys) - settings.min_unique)

    if settings.mode == "roster_feasibility":
        # Feasibility objective: maximize deterministic salary
        # utilization. This never claims to produce a good fantasy
        # lineup, only a legal one.
        model.Maximize(sum(used[k] * by_key[k].salary for k in used))
    else:
        # Real data only. candidate_pool was filtered to
        # player_is_eligible_for_mode() OR always_included_keys above --
        # a force-locked/pinned player (NFL M14 late swap) can be in
        # `used` WITHOUT the data this mode needs, so this only scores
        # players who actually have it, never fabricating a value for
        # the rest (they still count toward salary/slot/stack
        # constraints via `used`, just contribute 0 to the objective).
        objective_terms = [
            used[k] * scaled_objective_value(by_key[k], settings.mode)
            for k in used if player_is_eligible_for_mode(by_key[k], settings.mode)
        ]
        model.Maximize(sum(objective_terms))

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


def _check_mode_coverage(eligible_players: List[NflOptimizerPlayer], excluded_keys: Set[str], mode: str) -> List[str]:
    """Returns a list of specific, human-readable reasons real data
    coverage for `mode` can't fill every roster slot -- e.g. "0 QB(s)
    with a real Big Money Native projection available (need 1)". Empty
    list means every base slot has at least enough eligible players
    (not a full feasibility guarantee -- CP-SAT still does the real
    combinatorial check -- just the same cheap, specific pre-check
    optimizer/constraints.py::_concrete_infeasibility_reasons() does
    for MLB)."""
    candidate_pool = [p for p in eligible_players if p.key not in excluded_keys]
    label = "a real Big Money Native projection" if mode == "projection" else "a real Big Money Native projection and ceiling"
    reasons: List[str] = []
    for slot in DK_NFL_CLASSIC_ROSTER_SLOTS:
        base_slot = slot["slot"]
        available = eligible_for_slot(base_slot, candidate_pool)
        if len(available) < slot["count"]:
            reasons.append(f"Only {len(available)} {base_slot} player(s) with {label} available (need {slot['count']}).")
    return reasons


def _build_lineup(index: int, assignment: List[Tuple[str, NflOptimizerPlayer]], settings: NflOptimizerSettings) -> NflLineup:
    assignments = [
        NflLineupSlotAssignment(
            slot=slot, draftkings_player_id=p.key, name=p.name, position=p.position, team=p.team, salary=p.salary,
            projected_ownership=p.projected_ownership, ceiling=p.ceiling,
        )
        for slot, p in assignment
    ]
    total_salary = sum(a.salary for a in assignments)

    # NFL M14: a force-locked/pinned player (late swap) can be present
    # with no real projection -- only sum when EVERY assigned player has
    # one, exactly like total_ceiling/sum_ownership below, never a
    # partial sum silently presented as the whole lineup's total.
    is_scoring_mode = settings.mode in NFL_SCORING_OBJECTIVE_MODES
    projections = [p.projection for _, p in assignment if p.projection is not None]
    total_projection = round(sum(projections), 2) if is_scoring_mode and len(projections) == len(assignment) else None

    ceilings = [p.ceiling for _, p in assignment if p.ceiling is not None]
    total_ceiling = round(sum(ceilings), 2) if len(ceilings) == len(assignment) else None

    ownerships = [p.projected_ownership for _, p in assignment if p.projected_ownership is not None]
    has_full_ownership = len(ownerships) == len(assignment)
    sum_ownership = round(sum(ownerships), 2) if has_full_ownership else None
    average_ownership = round(sum(ownerships) / len(ownerships), 2) if has_full_ownership else None

    total_leverage_score = None
    if settings.mode == "leverage":
        leverages = [p.leverage_score for _, p in assignment if p.leverage_score is not None]
        if len(leverages) == len(assignment):
            total_leverage_score = round(sum(leverages), 2)

    qb = next((p for _, p in assignment if p.position == "QB"), None)
    qb_stack_team: Optional[str] = None
    qb_stack_receiver_count = 0
    bring_back_player: Optional[str] = None
    if qb is not None:
        catchers = [p for _, p in assignment if p.position in QB_STACK_PASS_CATCHER_POSITIONS and p.team == qb.team]
        qb_stack_receiver_count = len(catchers)
        if catchers:
            qb_stack_team = qb.team
        bb = next((p for _, p in assignment if p.position in BRING_BACK_ELIGIBLE_POSITIONS and qb.opponent and p.team == qb.opponent), None)
        if bb is not None:
            bring_back_player = bb.name

    dst = next((p for _, p in assignment if p.position == "DST"), None)
    rb_dst_team: Optional[str] = None
    if dst is not None and any(p.position == "RB" and p.team == dst.team for _, p in assignment):
        rb_dst_team = dst.team

    first_player = assignment[0][1]
    return NflLineup(
        index=index, assignments=assignments, total_salary=total_salary,
        remaining_salary=settings.salary_cap - total_salary,
        draft_group_id=first_player.draft_group_id, slate_date=first_player.slate_date,
        mode=settings.mode, total_projection=total_projection, total_ceiling=total_ceiling,
        sum_ownership=sum_ownership, average_ownership=average_ownership, total_leverage_score=total_leverage_score,
        qb_stack_team=qb_stack_team, qb_stack_receiver_count=qb_stack_receiver_count,
        bring_back_player=bring_back_player, rb_dst_team=rb_dst_team,
    )


def generate_lineups(players: List[NflOptimizerPlayer], settings: NflOptimizerSettings) -> NflGenerationResult:
    """Generates up to settings.num_lineups distinct legal lineups.
    Raises NflOptimizerConfigError for a contradictory/unresolvable
    lock/exclude/exposure/stack setting BEFORE any solver call -- never
    silently drops one. Raises NflProjectionCoverageError (scoring modes
    only) when real data coverage can't fill every roster slot -- never
    silently returns an empty result or falls back to salary. Otherwise
    stops (without raising) and reports a specific stopped_reason when
    the solver itself can't find a legal lineup for the next slot (NFL
    M13: uses nfl/constraints.py::explain_infeasibility() for the first
    lineup's failure, so a stacking/bring-back/RB+DST misconfiguration
    is named specifically rather than a generic message).

    NFL M13: player exposure across the batch is enforced via the same
    "deadline forcing" greedy sequential heuristic MLB's optimizer/
    lineup_generator.py uses -- each lineup is solved independently, and
    running per-player counts feed dynamic locks (once a min-exposure
    player's remaining lineup count equals their remaining target) and
    dynamic excludes (once a max-exposure player hits their cap) into
    the NEXT solve. This is documented as best-effort/greedy, not a
    globally joint optimization, exactly like MLB's."""
    if settings.mode not in VALID_MODES:
        raise NflOptimizerConfigError(f"Unknown mode {settings.mode!r}; expected one of {sorted(VALID_MODES)}.")

    eligible, locked_keys, excluded_keys, max_exposure_by_key, min_exposure_by_key = resolve_nfl_settings(players, settings)

    if settings.mode in NFL_SCORING_OBJECTIVE_MODES:
        coverage_reasons = _check_mode_coverage(eligible, excluded_keys, settings.mode)
        if coverage_reasons:
            raise NflProjectionCoverageError(
                f"Real Big Money Native data coverage cannot fill every roster slot for objective mode {settings.mode!r} -- "
                "refusing to generate a lineup rather than silently falling back to salary or treating missing data as zero: "
                + " ".join(coverage_reasons)
            )

    by_key = {p.key: p for p in eligible}
    all_keys = list(by_key.keys())

    exposure_caps = compute_exposure_count_caps(max_exposure_by_key, settings.max_exposure_default, settings.num_lineups, all_keys)
    min_exposure_targets = compute_min_exposure_targets(min_exposure_by_key, settings.num_lineups)

    lineups: List[NflLineup] = []
    previous_keys_list: List[List[str]] = []
    exposure_counts: Dict[str, int] = {k: 0 for k in all_keys}
    stopped_reason: Optional[str] = None

    for i in range(1, settings.num_lineups + 1):
        lineups_remaining = settings.num_lineups - i + 1

        dynamic_excludes = set(excluded_keys)
        for key in all_keys:
            if exposure_counts[key] >= exposure_caps.get(key, settings.num_lineups):
                dynamic_excludes.add(key)

        dynamic_locks = set(locked_keys)
        for key, target in min_exposure_targets.items():
            remaining_needed = target - exposure_counts.get(key, 0)
            if remaining_needed > 0 and remaining_needed >= lineups_remaining:
                dynamic_locks.add(key)

        result = solve_single_lineup(
            eligible, settings, forced_locks=dynamic_locks, forced_excludes=dynamic_excludes, previous_lineups=previous_keys_list,
        )
        if result is None:
            if i == 1:
                reasons = explain_infeasibility(eligible, settings)
                stopped_reason = f"No legal lineup found for lineup #{i} (locks/excludes/uniqueness/salary cap/stacking together are unsatisfiable): " + " ".join(reasons)
            else:
                stopped_reason = (
                    f"Requested {settings.num_lineups} lineups but only {len(lineups)} unique legal lineup(s) could be "
                    f"generated under the current constraints (uniqueness/exposure/stack/locks)."
                )
            break

        lineup = _build_lineup(i, result, settings)
        lineups.append(lineup)
        previous_keys_list.append([p.key for _, p in result])
        for _, p in result:
            exposure_counts[p.key] = exposure_counts.get(p.key, 0) + 1

    return NflGenerationResult(lineups=lineups, requested=settings.num_lineups, generated=len(lineups), stopped_reason=stopped_reason)
