"""Slate-relative ranking, percentiles, and capped normalization.

Ownership is estimated RELATIVE TO THE SLATE (see CLAUDE.md's Milestone
10 goals): a $9,500 pitcher means something different depending on what
else is available that day. Every function here operates on the set of
active players present on ONE slate, never a fixed/global threshold.
"""

from typing import Dict, List, Tuple


def compute_ranks(id_value_pairs: List[Tuple[str, float]], descending: bool = True) -> Dict[str, int]:
    """1-based rank per id. Tied values share the same (lowest) rank,
    e.g. two-way tie for best both rank 1, next player ranks 3."""
    if not id_value_pairs:
        return {}
    ordered = sorted(id_value_pairs, key=lambda kv: kv[1], reverse=descending)
    ranks: Dict[str, int] = {}
    for i, (pid, value) in enumerate(ordered):
        if i > 0 and value == ordered[i - 1][1]:
            ranks[pid] = ranks[ordered[i - 1][0]]
        else:
            ranks[pid] = i + 1
    return ranks


def compute_percentiles(id_value_pairs: List[Tuple[str, float]]) -> Dict[str, float]:
    """id -> percentile in [0, 100]; higher input value = higher percentile
    (best player on the slate scores 100, worst scores 0). Ties receive
    the average percentile across their tied span. A single-player slate
    returns a neutral 50.0 -- there is nothing to rank against."""
    n = len(id_value_pairs)
    if n == 0:
        return {}
    if n == 1:
        return {id_value_pairs[0][0]: 50.0}

    ascending = sorted(id_value_pairs, key=lambda kv: kv[1])
    percentiles: Dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ascending[j + 1][1] == ascending[i][1]:
            j += 1
        avg_index = (i + j) / 2.0
        pct = 100.0 * avg_index / (n - 1)
        for k in range(i, j + 1):
            percentiles[ascending[k][0]] = pct
        i = j + 1
    return percentiles


def normalize_with_cap(raw_scores: Dict[str, float], target_sum: float, cap: float = 100.0,
                        max_iterations: int = 25) -> Dict[str, float]:
    """Scales `raw_scores` (all >= 0) so they sum to `target_sum`, then
    caps any player above `cap` and redistributes the excess
    proportionally among the remaining uncapped players (a standard
    waterfall), repeating until nothing overflows. Guarantees every
    output is in [0, cap] and the sum stays as close to target_sum as
    the cap allows (it can only fall short if EVERY player would need to
    be capped, which never happens at realistic MLB slate sizes)."""
    if not raw_scores:
        return {}

    remaining_ids = set(raw_scores.keys())
    result: Dict[str, float] = {}
    remaining_target = target_sum

    for _ in range(max_iterations):
        total_raw = sum(max(0.0, raw_scores[i]) for i in remaining_ids)
        if total_raw <= 0:
            share = remaining_target / len(remaining_ids) if remaining_ids else 0.0
            for i in remaining_ids:
                result[i] = min(cap, max(0.0, share))
            remaining_ids = set()
            break

        scaled = {i: max(0.0, raw_scores[i]) / total_raw * remaining_target for i in remaining_ids}
        overflow_ids = {i for i, v in scaled.items() if v > cap}
        if not overflow_ids:
            result.update(scaled)
            remaining_ids = set()
            break

        for i in overflow_ids:
            result[i] = cap
            remaining_target -= cap
        remaining_ids -= overflow_ids
        if not remaining_ids:
            break

    # Safety net: if max_iterations was exhausted with players still
    # unresolved (astronomically unlikely at real slate sizes), give them
    # an even, capped share rather than leaving them unset.
    if remaining_ids:
        share = remaining_target / len(remaining_ids)
        for i in remaining_ids:
            result[i] = min(cap, max(0.0, share))

    return {i: max(0.0, min(cap, v)) for i, v in result.items()}
