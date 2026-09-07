"""NFL M13 -- pre-solve filtering/validation, player grouping, and
exposure math shared by nfl/solver.py's single-lineup solve and
multi-lineup generation loop. Mirrors optimizer/constraints.py's exact
split of concerns (kept as its own file, not folded into nfl/solver.py,
so that file doesn't become a monolith as M13 grows it) -- ported
generically where MLB's own code has no baseball-specific coupling
(exposure math, lock/exclude bookkeeping), reimplemented where NFL's
shape genuinely differs (team/position grouping, stack diagnostics --
see nfl/solver.py's own module docstring for why MLB's stack/pitcher-
vs-hitter constraints don't translate directly)."""

import math
from typing import Dict, List, Set, Tuple

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS
from config.nfl_optimizer_config import BRING_BACK_ELIGIBLE_POSITIONS, QB_STACK_PASS_CATCHER_POSITIONS
from nfl.objective import player_is_eligible_for_mode
from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings, NflStackConfig


class NflOptimizerConfigError(ValueError):
    """A lock/exclude/exposure/stack setting is contradictory or
    unresolvable. Raised BEFORE any solver call -- never silently
    dropped or ignored."""


def group_by_team(players: List[NflOptimizerPlayer]) -> Dict[str, List[NflOptimizerPlayer]]:
    grouping: Dict[str, List[NflOptimizerPlayer]] = {}
    for p in players:
        grouping.setdefault(p.team, []).append(p)
    return grouping


def group_by_game(players: List[NflOptimizerPlayer]) -> Dict[str, List[NflOptimizerPlayer]]:
    grouping: Dict[str, List[NflOptimizerPlayer]] = {}
    for p in players:
        grouping.setdefault(p.game_id, []).append(p)
    return grouping


def pass_catchers_by_team(players: List[NflOptimizerPlayer]) -> Dict[str, List[NflOptimizerPlayer]]:
    grouping: Dict[str, List[NflOptimizerPlayer]] = {}
    for p in players:
        if p.position in QB_STACK_PASS_CATCHER_POSITIONS:
            grouping.setdefault(p.team, []).append(p)
    return grouping


def bring_back_candidates_by_team(players: List[NflOptimizerPlayer]) -> Dict[str, List[NflOptimizerPlayer]]:
    grouping: Dict[str, List[NflOptimizerPlayer]] = {}
    for p in players:
        if p.position in BRING_BACK_ELIGIBLE_POSITIONS:
            grouping.setdefault(p.team, []).append(p)
    return grouping


def rbs_by_team(players: List[NflOptimizerPlayer]) -> Dict[str, List[NflOptimizerPlayer]]:
    grouping: Dict[str, List[NflOptimizerPlayer]] = {}
    for p in players:
        if p.position == "RB":
            grouping.setdefault(p.team, []).append(p)
    return grouping


def validate_stack_config(stack: NflStackConfig) -> None:
    if stack.qb_stack_mode not in ("off", "single", "double"):
        raise NflOptimizerConfigError(f"Unknown qb_stack_mode {stack.qb_stack_mode!r}; expected 'off', 'single', or 'double'.")
    if stack.bring_back_mode not in ("off", "one"):
        raise NflOptimizerConfigError(f"Unknown bring_back_mode {stack.bring_back_mode!r}; expected 'off' or 'one'.")
    if stack.bring_back_mode != "off" and stack.qb_stack_mode == "off":
        raise NflOptimizerConfigError(
            "Bring-back requires a QB stack to bring the opponent back against -- enable qb_stack_mode "
            "('single' or 'double') before enabling bring_back_mode."
        )
    if stack.max_players_per_team is not None and stack.max_players_per_team < 1:
        raise NflOptimizerConfigError(f"max_players_per_team must be at least 1, got {stack.max_players_per_team}.")
    if stack.max_players_per_game is not None and stack.max_players_per_game < 1:
        raise NflOptimizerConfigError(f"max_players_per_game must be at least 1, got {stack.max_players_per_game}.")
    if stack.max_players_per_team is not None and stack.qb_stack_mode != "off":
        min_receivers = 1 if stack.qb_stack_mode == "single" else 2
        # QB + receivers alone already needs this many roster spots on
        # one team -- a lower cap makes the requested stack literally
        # impossible before any solve is attempted.
        if stack.max_players_per_team < 1 + min_receivers:
            raise NflOptimizerConfigError(
                f"max_players_per_team ({stack.max_players_per_team}) is too low for qb_stack_mode={stack.qb_stack_mode!r} "
                f"(needs at least {1 + min_receivers} players from the QB's own team: the QB plus {min_receivers} pass-catcher(s))."
            )


def resolve_nfl_settings(
    all_players: List[NflOptimizerPlayer], settings: NflOptimizerSettings,
) -> Tuple[List[NflOptimizerPlayer], List[str], Set[str], Dict[str, float], Dict[str, float]]:
    """Validates and resolves every lock/exclude/exposure/stack setting.
    Returns (eligible_players, locked_keys, excluded_keys,
    max_exposure_by_key, min_exposure_by_key). Raises
    NflOptimizerConfigError on any contradiction, BEFORE any solver call."""
    validate_stack_config(settings.stack)

    by_key = {p.key: p for p in all_players}
    locked_keys = list(settings.locks)
    excluded_keys = set(settings.excludes)

    unknown_locks = set(locked_keys) - by_key.keys()
    if unknown_locks:
        raise NflOptimizerConfigError(f"Locked player key(s) not found in pool: {sorted(unknown_locks)}.")
    unknown_excludes = excluded_keys - by_key.keys()
    if unknown_excludes:
        raise NflOptimizerConfigError(f"Excluded player key(s) not found in pool: {sorted(unknown_excludes)}.")

    conflict = set(locked_keys) & excluded_keys
    if conflict:
        names = [by_key[k].name for k in conflict]
        raise NflOptimizerConfigError(f"Player(s) both locked and excluded -- contradiction: {names}")

    roster_size = sum(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS)
    if len(locked_keys) > roster_size:
        raise NflOptimizerConfigError(
            f"{len(locked_keys)} players locked, but a DraftKings Classic NFL lineup only has {roster_size} roster spots."
        )

    eligible = [p for p in all_players if player_is_eligible_for_mode(p, settings.mode)]
    eligible_keys = {p.key for p in eligible}
    ineligible_locks = set(locked_keys) - eligible_keys
    if ineligible_locks:
        names = [by_key[k].name for k in ineligible_locks]
        raise NflOptimizerConfigError(
            f"Locked player(s) {names} have no usable data for objective mode {settings.mode!r} and cannot be locked into every lineup."
        )

    max_exposure_by_key: Dict[str, float] = {}
    for key, fraction in settings.max_exposure.items():
        if key not in by_key:
            raise NflOptimizerConfigError(f"max_exposure references unknown player key {key!r}.")
        if not (0.0 <= fraction <= 1.0):
            raise NflOptimizerConfigError(f"max_exposure for {by_key[key].name!r} must be between 0.0 and 1.0, got {fraction}.")
        if key in locked_keys and fraction < 1.0:
            raise NflOptimizerConfigError(
                f"{by_key[key].name!r} is locked (must appear in every lineup) but max_exposure caps it at "
                f"{fraction:.0%} -- contradiction."
            )
        max_exposure_by_key[key] = fraction

    min_exposure_by_key: Dict[str, float] = {}
    for key, fraction in settings.min_exposure.items():
        if key not in by_key:
            raise NflOptimizerConfigError(f"min_exposure references unknown player key {key!r}.")
        if not (0.0 <= fraction <= 1.0):
            raise NflOptimizerConfigError(f"min_exposure for {by_key[key].name!r} must be between 0.0 and 1.0, got {fraction}.")
        if key in excluded_keys:
            raise NflOptimizerConfigError(f"{by_key[key].name!r} is excluded but also has a min_exposure target -- contradiction.")
        min_exposure_by_key[key] = fraction

    return eligible, locked_keys, excluded_keys, max_exposure_by_key, min_exposure_by_key


def compute_exposure_count_caps(
    max_exposure_by_key: Dict[str, float], default_fraction: float, num_lineups: int, all_keys: List[str],
) -> Dict[str, int]:
    """Rounding convention: a max cap always rounds DOWN (truncation) --
    never exceed the requested ceiling. `fraction >= 1.0` maps to
    exactly num_lineups (avoids float-precision loss at "unrestricted").
    Mirrors optimizer/constraints.py::compute_exposure_count_caps() --
    pure, sport-agnostic dict math, ported unchanged."""
    caps = {}
    for key in all_keys:
        fraction = max_exposure_by_key.get(key, default_fraction)
        caps[key] = num_lineups if fraction >= 1.0 else int(fraction * num_lineups)
    return caps


def compute_min_exposure_targets(min_exposure_by_key: Dict[str, float], num_lineups: int) -> Dict[str, int]:
    """Rounding convention: a min target always rounds UP (ceiling) --
    guarantee at least the requested floor. Mirrors optimizer/
    constraints.py::compute_min_exposure_targets() -- ported unchanged."""
    return {key: math.ceil(fraction * num_lineups) for key, fraction in min_exposure_by_key.items()}


def _stack_infeasibility_reasons(eligible_players: List[NflOptimizerPlayer], stack: NflStackConfig) -> List[str]:
    reasons: List[str] = []
    if stack.qb_stack_mode == "off" and not stack.rb_dst_enabled:
        return reasons

    if stack.qb_stack_mode != "off":
        min_receivers = 1 if stack.qb_stack_mode == "single" else 2
        catchers = pass_catchers_by_team(eligible_players)
        qbs = [p for p in eligible_players if p.position == "QB"]
        satisfiable = [qb for qb in qbs if len(catchers.get(qb.team, [])) >= min_receivers]
        if not satisfiable:
            reasons.append(
                f"No eligible QB has {min_receivers}+ eligible same-team WR/TE for the requested "
                f"{'single' if min_receivers == 1 else 'double'} QB stack."
            )
        elif stack.bring_back_mode != "off":
            bring_back_pool = bring_back_candidates_by_team(eligible_players)
            still_satisfiable = [qb for qb in satisfiable if qb.opponent and len(bring_back_pool.get(qb.opponent, [])) >= 1]
            if not still_satisfiable:
                reasons.append(
                    "No eligible QB satisfying the stack requirement also has an opposing RB/WR/TE available for the bring-back."
                )

    if stack.rb_dst_enabled:
        dsts = [p for p in eligible_players if p.position == "DST"]
        rb_teams = rbs_by_team(eligible_players)
        if not any(dst.team in rb_teams for dst in dsts):
            reasons.append("No eligible DST has an eligible same-team RB for the requested RB+DST correlation.")

    return reasons


def _position_availability_reasons(eligible_players: List[NflOptimizerPlayer]) -> List[str]:
    by_slot: Dict[str, List[NflOptimizerPlayer]] = {slot["slot"]: [] for slot in DK_NFL_CLASSIC_ROSTER_SLOTS}
    for p in eligible_players:
        for slot_name in by_slot:
            if slot_name in p.roster_slots:
                by_slot[slot_name].append(p)
    reasons: List[str] = []
    for slot in DK_NFL_CLASSIC_ROSTER_SLOTS:
        available = by_slot.get(slot["slot"], [])
        if len(available) < slot["count"]:
            reasons.append(f"Only {len(available)} eligible {slot['slot']} player(s) available (need {slot['count']}).")
    return reasons


def _concrete_infeasibility_reasons(eligible_players: List[NflOptimizerPlayer], settings: NflOptimizerSettings) -> List[str]:
    """The individually-checkable blockers shared by explain_infeasibility()
    (called after a real solve fails) and a future proactive pre-solve
    panel. Never includes a generic fallback message -- an empty return
    means none of these specific checks found a problem."""
    reasons = _position_availability_reasons(eligible_players)
    reasons += _stack_infeasibility_reasons(eligible_players, settings.stack)
    # max_players_per_team/max_players_per_game constrain the SOLVE's
    # combinatorics (which specific players end up together), not raw
    # pool availability -- there's no cheap, specific pre-check for them
    # the way there is for "not enough eligible players at a slot at
    # all"; a genuine conflict there surfaces as a real solve failure,
    # caught by explain_infeasibility()'s generic fallback message below.
    return reasons


def explain_infeasibility(eligible_players: List[NflOptimizerPlayer], settings: NflOptimizerSettings) -> List[str]:
    """Best-effort human-readable reasons a solve came back infeasible.
    Not exhaustive (CP-SAT doesn't hand back a minimal conflict set for
    free) -- covers the common, individually-checkable blockers.
    Mirrors optimizer/constraints.py::explain_infeasibility()."""
    reasons = _concrete_infeasibility_reasons(eligible_players, settings)
    if not reasons:
        reasons.append(
            "Position, salary-cap, stacking, bring-back, RB+DST, team/game-limit, lock, and exclude rules each look "
            "individually satisfiable, but no combination of them together is legal."
        )
    return reasons
