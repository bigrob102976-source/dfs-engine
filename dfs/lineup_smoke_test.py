"""One deterministic smoke test: can we construct a single legal
DraftKings Classic MLB lineup from the active pool, under the salary
cap? This is NOT the optimizer -- no objective function, no stacking, no
exposure rules, no multiple lineups. It exists solely to prove the
player pool and roster rules are internally coherent before the real
optimizer (next milestone) is built on top of them.
"""

from typing import List, Optional

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
) -> Optional[List[DFSPlayer]]:
    """Deterministic backtracking search for ONE legal lineup (9 unique
    players, correct position counts per slot, total salary <= cap).
    Cheapest-eligible-candidate-first ordering leaves the most salary
    headroom for later slots. Returns None if no legal lineup exists, or
    if the search gives up after `max_nodes` expansions (a safety valve
    -- not a proof of infeasibility, just a bound on effort for a smoke
    test that isn't meant to be the real optimizer)."""
    by_slot_candidates = {
        slot: sorted(_eligible_for_slot(slot, active_pool), key=lambda p: (p.salary, p.dk_player_id))
        for slot in set(_SLOT_ORDER)
    }

    used_ids: set = set()
    lineup: List[DFSPlayer] = []
    nodes = [0]

    def backtrack(slot_index: int, salary_used: int) -> bool:
        if slot_index == len(_SLOT_ORDER):
            return True
        nodes[0] += 1
        if nodes[0] > max_nodes:
            return False
        slot = _SLOT_ORDER[slot_index]
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

    return list(lineup) if backtrack(0, 0) else None
