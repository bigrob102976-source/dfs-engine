"""Independent post-hoc lineup validation. The solver's own constraints
are trusted to produce legal output, but this module re-derives every
check from scratch against the raw player pool -- never assumes solver
success implies legality. Any future solver bug should be caught here,
not silently shipped in a saved lineup file.
"""

from typing import Dict, List, Optional, Set

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_ROSTER_SIZE
from optimizer.constraints import pitcher_vs_hitter_conflicts
from optimizer.models import Lineup, OptimizerPlayer, OptimizerSettings


def _hitter_team_counts(lineup: Lineup, players_by_key: Dict[str, OptimizerPlayer]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for a in lineup.assignments:
        player = players_by_key.get(a.dk_player_id)
        if player and player.player_type == "hitter":
            counts[a.team] = counts.get(a.team, 0) + 1
    return counts


def validate_lineup(
    lineup: Lineup, players_by_key: Dict[str, OptimizerPlayer], settings: OptimizerSettings,
    locked_keys=(), excluded_keys=(),
) -> List[str]:
    violations: List[str] = []
    keys = [a.dk_player_id for a in lineup.assignments]

    if len(lineup.assignments) != DK_ROSTER_SIZE:
        violations.append(f"Roster size is {len(lineup.assignments)}, expected {DK_ROSTER_SIZE}.")

    slot_counts: Dict[str, int] = {}
    for a in lineup.assignments:
        slot_counts[a.slot] = slot_counts.get(a.slot, 0) + 1
    for slot in DK_CLASSIC_ROSTER_SLOTS:
        actual = slot_counts.get(slot["slot"], 0)
        if actual != slot["count"]:
            violations.append(f"Slot {slot['slot']}: {actual} filled, expected {slot['count']}.")

    if len(keys) != len(set(keys)):
        violations.append("Duplicate player(s) in lineup.")

    for a in lineup.assignments:
        player = players_by_key.get(a.dk_player_id)
        if player is None:
            violations.append(f"{a.name}: not found in the active player pool used to build this lineup.")
            continue
        if a.slot == "P":
            if player.player_type != "pitcher":
                violations.append(f"{a.name}: assigned to slot P but is not a pitcher.")
        elif a.slot not in player.dk_positions:
            violations.append(f"{a.name}: not DK-eligible for slot {a.slot} (eligible: {player.dk_positions}).")

    if lineup.salary > settings.salary_cap:
        violations.append(f"Salary {lineup.salary} exceeds cap {settings.salary_cap}.")

    if settings.min_salary is not None and lineup.salary < settings.min_salary:
        violations.append(f"Salary {lineup.salary} is below the minimum spend {settings.min_salary}.")

    for key in locked_keys:
        if key not in keys:
            player = players_by_key.get(key)
            violations.append(f"Locked player {player.name if player else key} missing from lineup.")

    for key in excluded_keys:
        if key in keys:
            player = players_by_key.get(key)
            violations.append(f"Excluded player {player.name if player else key} present in lineup.")

    hitter_team_counts = _hitter_team_counts(lineup, players_by_key)
    if settings.stack_size:
        if settings.stack_team:
            if hitter_team_counts.get(settings.stack_team, 0) < settings.stack_size:
                violations.append(f"Stack requirement not met for {settings.stack_team} (need {settings.stack_size}).")
        else:
            if not hitter_team_counts or max(hitter_team_counts.values()) < settings.stack_size:
                violations.append(f"No team meets the required stack size of {settings.stack_size}.")

    if not settings.allow_pitcher_vs_hitter:
        conflicts = pitcher_vs_hitter_conflicts(list(players_by_key.values()))
        for a in lineup.assignments:
            if a.slot == "P" and a.dk_player_id in conflicts:
                bad = set(conflicts[a.dk_player_id]) & set(keys)
                if bad:
                    bad_names = [players_by_key[k].name for k in bad if k in players_by_key]
                    violations.append(f"Pitcher {a.name} shares the lineup with opposing hitter(s) he faces: {bad_names}.")

    for team, count in hitter_team_counts.items():
        if count > settings.team_max_hitters:
            violations.append(f"{team}: {count} hitters exceeds team max of {settings.team_max_hitters}.")

    if settings.max_total_ownership is not None and lineup.sum_ownership is not None:
        if lineup.sum_ownership > settings.max_total_ownership:
            violations.append(
                f"Sum of projected ownership {lineup.sum_ownership} exceeds --max-total-ownership {settings.max_total_ownership}."
            )

    return violations


def validate_lineup_set(
    lineups: List[Lineup], players_by_key: Dict[str, OptimizerPlayer], settings: OptimizerSettings,
    locked_keys: Set[str] = frozenset(), excluded_keys: Set[str] = frozenset(),
    max_exposure_caps: Optional[Dict[str, int]] = None, min_unique: int = 1,
) -> Dict[int, List[str]]:
    """Per-lineup checks plus set-level checks (exposure compliance,
    pairwise uniqueness)."""
    results: Dict[int, List[str]] = {
        lineup.index: validate_lineup(lineup, players_by_key, settings, locked_keys, excluded_keys) for lineup in lineups
    }

    if max_exposure_caps:
        counts: Dict[str, int] = {}
        for lineup in lineups:
            for key in lineup.player_keys():
                counts[key] = counts.get(key, 0) + 1
        for key, cap in max_exposure_caps.items():
            if counts.get(key, 0) > cap:
                name = players_by_key[key].name if key in players_by_key else key
                for lineup in lineups:
                    if key in lineup.player_keys():
                        results.setdefault(lineup.index, []).append(
                            f"Exposure cap exceeded for {name}: appears in {counts[key]} lineups (cap {cap})."
                        )

    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            shared = set(a.player_keys()) & set(b.player_keys())
            diff = DK_ROSTER_SIZE - len(shared)
            if diff < min_unique:
                results.setdefault(a.index, []).append(
                    f"Lineup {a.index} and lineup {b.index} differ by only {diff} player(s) (min_unique={min_unique})."
                )

    return results
