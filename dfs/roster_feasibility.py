"""Validates whether a legal DraftKings Classic MLB lineup is even
theoretically possible from the active player pool -- position coverage
and pitcher count only. This is validation, not optimization: it never
picks a lineup or scores anything, it just answers PASS/FAIL with reasons.
"""

from typing import List

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_MIN_GAMES_REPRESENTED
from dfs.models import DFSPlayer, RosterFeasibilityResult


def check_roster_feasibility(active_pool: List[DFSPlayer]) -> RosterFeasibilityResult:
    reasons: List[str] = []
    position_counts = {}

    pitcher_count = sum(1 for p in active_pool if p.player_type == "pitcher")
    pitcher_slot = next(s for s in DK_CLASSIC_ROSTER_SLOTS if s["slot"] == "P")
    position_counts["P"] = pitcher_count
    if pitcher_count < pitcher_slot["count"]:
        reasons.append(f"Only {pitcher_count} eligible pitcher(s) in active pool (need {pitcher_slot['count']})")

    for slot in DK_CLASSIC_ROSTER_SLOTS:
        if slot["slot"] == "P":
            continue
        eligible = [p for p in active_pool if p.player_type == "hitter"
                    and any(pos in slot["eligible_positions"] for pos in p.dk_positions)]
        position_counts[slot["slot"]] = len(eligible)
        if len(eligible) < slot["count"]:
            reasons.append(f"Only {len(eligible)} eligible {slot['slot']}(s) in active pool (need {slot['count']})")

    games_represented = len({p.game_id for p in active_pool if p.game_id})
    if games_represented < DK_MIN_GAMES_REPRESENTED:
        reasons.append(
            f"Active pool only spans {games_represented} game(s); DraftKings Classic MLB requires "
            f"players from at least {DK_MIN_GAMES_REPRESENTED}"
        )

    return RosterFeasibilityResult(
        passed=not reasons, reasons=reasons, position_counts=position_counts,
        pitcher_count=pitcher_count, games_represented=games_represented,
    )
