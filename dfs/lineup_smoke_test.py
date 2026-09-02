"""One deterministic smoke test: can we construct a single legal
DraftKings Classic MLB lineup from the active pool, under the salary
cap? This is NOT the optimizer -- no objective function, no stacking, no
exposure rules. It exists solely to prove the player pool and roster
rules are internally coherent before the real optimizer is built on top
of them.

M6L: also the honest, non-projection structural proof that a canonical-
Postgres-sourced pool (real salaries/positions/eligibility, but no
projection source -- see canonicalPostgresBackend.ts's own scope-gap
docstring) can produce a REAL, legal DK roster -- locks/excludes/
multiple-lineups-with-uniqueness included -- without the real CP-SAT
optimizer (scripts/optimize_dk_lineups.py), which requires a real
per-player projection/ceiling and therefore cannot honestly run against
canonical data yet (M6M: never fabricate one merely to force a build
through). locked_player_ids/excluded_player_ids/find_lineups are
additive to this file's own pre-existing, already-tested
find_one_legal_lineup -- every existing call site's behavior is
unchanged (both new parameters default to None).
"""

from typing import List, Optional, Set

from config.dk_roster_config import DK_CLASSIC_SALARY_CAP
from dfs.models import DFSPlayer

# Scarcest positions first, so an infeasible branch is discovered (and
# backtracked out of) as early as possible.
_SLOT_ORDER = ["C", "SS", "3B", "2B", "1B", "OF", "OF", "OF", "P", "P"]


def _eligible_for_slot(slot: str, pool: List[DFSPlayer]) -> List[DFSPlayer]:
    if slot == "P":
        return [p for p in pool if p.player_type == "pitcher"]
    return [p for p in pool if p.player_type == "hitter" and slot in p.dk_positions]


def find_one_legal_lineup(
    active_pool: List[DFSPlayer], salary_cap: int = DK_CLASSIC_SALARY_CAP, max_nodes: int = 200_000,
    locked_player_ids: Optional[Set[str]] = None, excluded_player_ids: Optional[Set[str]] = None,
) -> Optional[List[DFSPlayer]]:
    """Deterministic backtracking search for ONE legal lineup (9 unique
    players, correct position counts per slot, total salary <= cap).
    Cheapest-eligible-candidate-first ordering leaves the most salary
    headroom for later slots. Returns None if no legal lineup exists, or
    if the search gives up after `max_nodes` expansions (a safety valve
    -- not a proof of infeasibility, just a bound on effort for a smoke
    test that isn't meant to be the real optimizer).

    M6L: `excluded_player_ids` are removed from the candidate pool
    before the search begins. `locked_player_ids` are greedily assigned
    first -- each locked player takes the cheapest still-open slot they
    are eligible for (a simplification appropriate for a structural
    smoke test, NOT the real optimizer's own constraint-satisfaction
    treatment of locks) -- and the remaining slots are then backtracked
    normally against the remaining pool/budget. Returns None (never
    guesses/drops a lock) if a locked player has no open eligible slot,
    or two locked players require the same single-instance slot."""
    excluded = excluded_player_ids or set()
    pool = [p for p in active_pool if p.dk_player_id not in excluded]

    remaining_slots = list(_SLOT_ORDER)
    fixed: List[DFSPlayer] = []
    fixed_ids: set = set()
    fixed_salary = 0

    if locked_player_ids:
        by_id = {p.dk_player_id: p for p in pool}
        for locked_id in sorted(locked_player_ids):
            player = by_id.get(locked_id)
            if player is None or locked_id in fixed_ids:
                return None
            open_slots = [s for s in set(remaining_slots) if player in _eligible_for_slot(s, [player])]
            if not open_slots:
                return None
            # Cheapest-eligible-slot-availability-first is irrelevant for
            # a single player -- just take the first eligible open slot,
            # preferring the scarcest (earliest in _SLOT_ORDER) for
            # multi-eligibility players (e.g. a real DK 1B/3B).
            chosen_slot = next(s for s in remaining_slots if s in open_slots)
            remaining_slots.remove(chosen_slot)
            fixed.append(player)
            fixed_ids.add(locked_id)
            fixed_salary += player.salary

    if fixed_salary > salary_cap:
        return None

    by_slot_candidates = {
        slot: sorted(_eligible_for_slot(slot, pool), key=lambda p: (p.salary, p.dk_player_id))
        for slot in set(remaining_slots)
    }

    used_ids: set = set(fixed_ids)
    lineup: List[DFSPlayer] = []
    nodes = [0]

    def backtrack(slot_index: int, salary_used: int) -> bool:
        if slot_index == len(remaining_slots):
            return True
        nodes[0] += 1
        if nodes[0] > max_nodes:
            return False
        slot = remaining_slots[slot_index]
        for candidate in by_slot_candidates[slot]:
            if candidate.dk_player_id in used_ids:
                continue
            if salary_used + candidate.salary > salary_cap:
                continue
            used_ids.add(candidate.dk_player_id)
            lineup.append(candidate)
            if backtrack(slot_index + 1, salary_used + candidate.salary):
                return True
            lineup.pop()
            used_ids.remove(candidate.dk_player_id)
        return False

    if not backtrack(0, fixed_salary):
        return None
    return fixed + lineup


def find_lineups(
    active_pool: List[DFSPlayer], count: int, salary_cap: int = DK_CLASSIC_SALARY_CAP, max_nodes: int = 200_000,
    locked_player_ids: Optional[Set[str]] = None, excluded_player_ids: Optional[Set[str]] = None,
) -> List[List[DFSPlayer]]:
    """M6L: `count` DISTINCT legal lineups (never the real optimizer's
    own exposure/min-unique rules -- a simple, honest "no two returned
    lineups are identical" uniqueness guarantee for a structural-only
    proof). Stops early (returns fewer than `count`) once no further
    distinct legal lineup can be found -- never fabricates a duplicate
    or an illegal one to reach the requested count."""
    results: List[List[DFSPlayer]] = []
    seen_ids: List[frozenset] = []
    already_excluded = set(excluded_player_ids or set())

    for _ in range(count):
        lineup = find_one_legal_lineup(
            active_pool, salary_cap=salary_cap, max_nodes=max_nodes,
            locked_player_ids=locked_player_ids, excluded_player_ids=already_excluded,
        )
        if lineup is None:
            break
        ids = frozenset(p.dk_player_id for p in lineup)
        if ids in seen_ids:
            break
        results.append(lineup)
        seen_ids.append(ids)
        # Force the NEXT search away from this exact roster (uniqueness)
        # by excluding one non-locked player from it -- the cheapest
        # eligible one, so the next lineup differs by at least one real
        # roster spot without over-constraining the remaining search.
        removable = [p for p in lineup if not (locked_player_ids and p.dk_player_id in locked_player_ids)]
        if not removable:
            break
        cheapest = min(removable, key=lambda p: (p.salary, p.dk_player_id))
        already_excluded = already_excluded | {cheapest.dk_player_id}

    return results
