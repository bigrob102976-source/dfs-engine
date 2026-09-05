"""NFL M14 -- late swap: reuses nfl/solver.py's EXISTING CP-SAT engine.
Translates a saved lineup's LOCKED slots (real game_start_utc has
passed, per nfl/game_lock.py) into hard slot-pinned constraints
(nfl/solver.py::solve_single_lineup's forced_slot_assignments), then
re-solves ONLY the unlocked slots against the current player pool,
projections, ownership, and status. Never a second/duplicate optimizer
-- see nfl/solver.py's own docstring for the shared engine.

Core guarantees (NFL M14 Phase 6):
  - a locked player is ALWAYS present in the result, in the SAME slot
  - a locked player's current status/exclusion/exposure settings never
    remove them -- status-based and explicit exclusion apply to
    UNLOCKED players only
  - salary/roster/stack constraints are re-checked against the WHOLE
    lineup (locked + unlocked together), never just the unlocked part
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from nfl.game_lock import is_locked
from nfl.optimizer_models import NflLineup, NflOptimizerPlayer, NflOptimizerSettings
from nfl.saved_lineup_models import NflSavedLineup, NflSavedLineupSlot, validate_saved_lineup
from nfl.solver import _build_lineup, solve_single_lineup
from nfl.status import DEFAULT_EXCLUDE_BY_STATUS, normalize_status

class LateSwapError(RuntimeError):
    """Raised BEFORE any solve when the request itself is unsafe to run
    -- e.g. the current pool is for a different DraftGroup entirely
    (NFL M14 Phase 23's "stale saved lineup from wrong DraftGroup" case)."""


_BASE_SLOT_FOR_INSTANCE = {
    "QB": "QB", "TE": "TE", "FLEX": "FLEX", "DST": "DST",
    "RB1": "RB", "RB2": "RB", "WR1": "WR", "WR2": "WR", "WR3": "WR",
}


@dataclass
class LateSwapResult:
    lineup: Optional[NflLineup]
    locked_slots: List[str]  # roster_slot labels, e.g. ["QB", "RB1"]
    unlocked_slots: List[str]
    changed_player_keys: List[str]  # unlocked-slot players whose identity differs from the saved lineup
    fully_locked: bool
    error: Optional[str] = None


def classify_slots(saved: NflSavedLineup, now_utc: datetime) -> Tuple[List[NflSavedLineupSlot], List[NflSavedLineupSlot]]:
    """Returns (locked_slots, unlocked_slots), computed FRESH from each
    slot's real game_start_utc against now_utc -- never a stored boolean."""
    locked, unlocked = [], []
    for slot in saved.slots:
        if is_locked(slot.game_start_utc, now_utc):
            locked.append(slot)
        else:
            unlocked.append(slot)
    return locked, unlocked


def _synthetic_player_from_snapshot(slot: NflSavedLineupSlot, draft_group_id: int, slate_date: str) -> NflOptimizerPlayer:
    """Reconstructs a minimal NflOptimizerPlayer from a LOCKED slot's own
    saved snapshot -- used only when that player has since disappeared
    from the current live pool (a rare, defensive case; NFL M14 Phase
    23). Every field is the player's own real recorded data, never
    invented. roster_slots is deliberately minimal (just the base slot
    they occupied) -- sufficient because this player is pinned to that
    one exact slot and is never a candidate for any other."""
    base_slot = _BASE_SLOT_FOR_INSTANCE.get(slot.roster_slot, slot.roster_slot)
    return NflOptimizerPlayer(
        key=slot.draftkings_player_id, name=slot.name, team=slot.team, opponent=slot.opponent,
        game_id=slot.game_id, position=slot.position, roster_slots=[base_slot],
        salary=slot.salary, is_team_entity=(slot.position == "DST"), draft_group_id=draft_group_id,
        slate_date=slate_date, projection=slot.projection_snapshot, ceiling=slot.ceiling_snapshot,
        projected_ownership=slot.ownership_snapshot, game_start_time=slot.game_start_utc,
    )


def run_late_swap(
    saved: NflSavedLineup,
    current_pool: List[NflOptimizerPlayer],
    settings: NflOptimizerSettings,
    now_utc: datetime,
    exclude_by_status: Optional[Dict[str, bool]] = None,
) -> LateSwapResult:
    """`settings` carries the objective mode/stack/exposure to use for
    the UNLOCKED slots -- locks/excludes on it are merged with (never
    override) the saved lineup's own locked players."""
    validate_saved_lineup(saved)

    if current_pool and saved.draft_group_id not in {p.draft_group_id for p in current_pool}:
        raise LateSwapError(
            f"Saved lineup is for DraftGroup {saved.draft_group_id}, but the current pool is for a different "
            "DraftGroup entirely -- refusing to late-swap a stale lineup against the wrong slate."
        )

    locked_slots, unlocked_slots = classify_slots(saved, now_utc)
    locked_keys = {s.draftkings_player_id for s in locked_slots}

    if not unlocked_slots:
        return LateSwapResult(
            lineup=None, locked_slots=[s.roster_slot for s in locked_slots], unlocked_slots=[],
            changed_player_keys=[], fully_locked=True,
        )

    pool_by_key = {p.key: p for p in current_pool}
    candidate_pool = list(current_pool)
    for slot in locked_slots:
        if slot.draftkings_player_id not in pool_by_key:
            candidate_pool.append(_synthetic_player_from_snapshot(slot, saved.draft_group_id, saved.slate_date))

    # Status-based + explicit exclusion applies ONLY to unlocked players
    # -- a locked player's current status can never remove them (NFL
    # M14 Phase 6/15's explicit requirement).
    policy = exclude_by_status or DEFAULT_EXCLUDE_BY_STATUS
    status_excluded = {
        p.key for p in candidate_pool
        if p.key not in locked_keys and policy.get(normalize_status(p.raw_status), False)
    }
    explicit_excludes = {k for k in settings.excludes if k not in locked_keys}
    forced_excludes = status_excluded | explicit_excludes

    forced_slot_assignments = {s.roster_slot: s.draftkings_player_id for s in locked_slots}

    swap_settings = NflOptimizerSettings(
        mode=settings.mode, num_lineups=1, min_unique=settings.min_unique,
        locks=list(locked_keys) + [k for k in settings.locks if k not in locked_keys],
        excludes=list(forced_excludes), salary_cap=settings.salary_cap,
        time_limit_seconds=settings.time_limit_seconds, stack=settings.stack,
        max_exposure=settings.max_exposure, max_exposure_default=settings.max_exposure_default,
        min_exposure=settings.min_exposure,
    )

    result = solve_single_lineup(
        candidate_pool, swap_settings, forced_locks=locked_keys, forced_excludes=forced_excludes,
        forced_slot_assignments=forced_slot_assignments,
    )
    if result is None:
        return LateSwapResult(
            lineup=None, locked_slots=[s.roster_slot for s in locked_slots],
            unlocked_slots=[s.roster_slot for s in unlocked_slots], changed_player_keys=[], fully_locked=False,
            error="No legal lineup exists for the unlocked slots given the locked players' salary usage, "
                  "current status/exclusions, and requested stacking/exposure settings together.",
        )

    lineup = _build_lineup(0, result, swap_settings)
    locked_slot_labels = {s.roster_slot for s in locked_slots}
    original_unlocked_keys = {s.draftkings_player_id for s in unlocked_slots}
    new_unlocked_keys = {a.draftkings_player_id for a in lineup.assignments if a.slot not in locked_slot_labels}
    changed = sorted((original_unlocked_keys - new_unlocked_keys) | (new_unlocked_keys - original_unlocked_keys))

    return LateSwapResult(
        lineup=lineup, locked_slots=[s.roster_slot for s in locked_slots],
        unlocked_slots=[s.roster_slot for s in unlocked_slots], changed_player_keys=changed, fully_locked=False,
    )
