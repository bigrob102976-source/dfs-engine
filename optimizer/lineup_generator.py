"""Sequential multi-lineup generation: solves one lineup at a time,
adding a uniqueness constraint against every lineup already generated
and dynamically excluding/forcing players as running exposure counts
hit their caps/targets. No randomness -- the same pool and settings
always walk through the same sequence of solves in the same order.

Min-exposure is handled by a simple "deadline forcing" heuristic: once
the number of lineups remaining equals the number of appearances a
player still needs to hit their target, that player is temporarily
locked for the rest of generation. This reuses the existing lock
mechanism rather than a separate joint optimization, which is why the
milestone's "defer if it significantly complicates things" escape hatch
wasn't needed -- it's a best-effort greedy guarantee, not a globally
optimal one, and is documented as such.
"""

from typing import Dict, List, Tuple

from config.ownership_config import CHALK_OWNERSHIP_THRESHOLD
from optimizer.constraints import (
    compute_exposure_count_caps,
    compute_min_exposure_targets,
    explain_infeasibility,
    resolve_settings,
)
from optimizer.models import GenerationOutput, GenerationResult, Lineup, LineupPlayerAssignment, OptimizerPlayer, OptimizerSettings
from optimizer.solver import solve_single_lineup


def _build_lineup(index: int, assignment: List[Tuple[str, OptimizerPlayer]], settings: OptimizerSettings) -> Lineup:
    assignments = [
        LineupPlayerAssignment(
            slot=slot, dk_player_id=player.key, mlb_player_id=player.mlb_player_id, name=player.name,
            team=player.team, opponent=player.opponent, salary=player.salary, projection=player.projection,
            ceiling=player.ceiling, floor=player.floor, risk_score=player.risk_score, confidence=player.confidence,
            projected_ownership=player.projected_ownership,
        )
        for slot, player in assignment
    ]
    salary = sum(a.salary for a in assignments)
    projection = sum(a.projection for a in assignments)
    ceiling = sum(a.ceiling for a in assignments)
    floors = [a.floor for a in assignments if a.floor is not None]
    risks = [a.risk_score for a in assignments if a.risk_score is not None]
    confidences = [a.confidence for a in assignments if a.confidence is not None]

    team_counts: Dict[str, int] = {}
    hitter_team_counts: Dict[str, int] = {}
    for slot, player in assignment:
        team_counts[player.team] = team_counts.get(player.team, 0) + 1
        if player.player_type == "hitter":
            hitter_team_counts[player.team] = hitter_team_counts.get(player.team, 0) + 1

    if hitter_team_counts:
        primary_stack_team = max(hitter_team_counts, key=lambda t: hitter_team_counts[t])
        primary_stack_size = hitter_team_counts[primary_stack_team]
    else:
        primary_stack_team, primary_stack_size = None, 0

    # Multi-team stacks (M2): report the requested secondary team's own
    # actual hitter count -- not "whichever team has the second-most
    # hitters" (that could be a team never requested at all).
    if settings.stack_team_2:
        secondary_stack_team = settings.stack_team_2
        secondary_stack_size = hitter_team_counts.get(settings.stack_team_2, 0)
    else:
        secondary_stack_team, secondary_stack_size = None, 0

    ownerships = [a.projected_ownership for a in assignments if a.projected_ownership is not None]
    has_full_ownership = len(ownerships) == len(assignments)
    sum_ownership = round(sum(ownerships), 2) if has_full_ownership else None
    average_ownership = round(sum(ownerships) / len(ownerships), 2) if has_full_ownership else None
    max_ownership = round(max(ownerships), 2) if has_full_ownership else None
    chalk_count = sum(1 for o in ownerships if o >= CHALK_OWNERSHIP_THRESHOLD) if has_full_ownership else None

    return Lineup(
        index=index, assignments=assignments, salary=salary,
        remaining_salary=settings.salary_cap - salary,
        projection=round(projection, 2), ceiling=round(ceiling, 2),
        floor=round(sum(floors), 2) if floors else 0.0,
        average_risk=round(sum(risks) / len(risks), 2) if risks else None,
        average_confidence=round(sum(confidences) / len(confidences), 2) if confidences else None,
        team_counts=team_counts, primary_stack_team=primary_stack_team, primary_stack_size=primary_stack_size,
        secondary_stack_team=secondary_stack_team, secondary_stack_size=secondary_stack_size,
        sum_ownership=sum_ownership, average_ownership=average_ownership, max_ownership=max_ownership,
        players_above_chalk_threshold=chalk_count,
    )


def generate_lineups(all_active_players: List[OptimizerPlayer], settings: OptimizerSettings) -> GenerationOutput:
    eligible, locked_keys, excluded_keys, max_exposure_by_key, min_exposure_by_key = resolve_settings(
        all_active_players, settings
    )
    players_by_key = {p.key: p for p in eligible}
    all_keys = list(players_by_key.keys())

    exposure_caps = compute_exposure_count_caps(max_exposure_by_key, settings.max_exposure_default, settings.num_lineups, all_keys)
    min_exposure_targets = compute_min_exposure_targets(min_exposure_by_key, settings.num_lineups)

    generated: List[Lineup] = []
    previous_key_lists: List[List[str]] = []
    exposure_counts: Dict[str, int] = {k: 0 for k in all_keys}
    stopped_reason = None

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

        assignment = solve_single_lineup(
            eligible, settings, forced_locks=dynamic_locks, forced_excludes=dynamic_excludes,
            previous_lineups=previous_key_lists,
        )

        if assignment is None:
            if i == 1:
                reasons = explain_infeasibility(eligible, settings)
                stopped_reason = "No legal lineup exists: " + " ".join(reasons)
            else:
                stopped_reason = (
                    f"Requested {settings.num_lineups} lineups but only {len(generated)} unique legal lineup(s) "
                    f"could be generated under the current constraints (uniqueness/exposure/stack/locks)."
                )
            break

        lineup = _build_lineup(i, assignment, settings)
        generated.append(lineup)
        previous_key_lists.append(lineup.player_keys())
        for key in lineup.player_keys():
            exposure_counts[key] = exposure_counts.get(key, 0) + 1

    result = GenerationResult(
        lineups=generated, requested=settings.num_lineups, generated=len(generated), stopped_reason=stopped_reason
    )
    return GenerationOutput(
        result=result, players_by_key=players_by_key, locked_keys=locked_keys, excluded_keys=excluded_keys,
        exposure_caps=exposure_caps, min_exposure_targets=min_exposure_targets,
    )
