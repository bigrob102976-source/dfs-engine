"""Pre-solve filtering, player-name resolution, and settings validation
shared by the single-lineup solver and the multi-lineup generator.

Nothing here touches projections -- --min-confidence / --min-season-pa /
--max-player-risk / --max-player-ownership / --min-player-ownership only
decide which already-scored players are eligible for lineup construction.
This is deliberately a lineup-construction concern, not a Batter/Pitcher
Agent or ownership-model concern (see CLAUDE.md's separation of "model
predictions" from "AI interpretation"/"decision making").
"""

import math
from typing import Dict, List, Set, Tuple

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_ROSTER_SIZE
from dfs.name_normalization import normalize_name
from optimizer.models import OptimizerPlayer, OptimizerSettings


class OptimizerConfigError(ValueError):
    """A lock/exclude/exposure setting is contradictory or unresolvable.
    Raised BEFORE any solver call -- never silently dropped or ignored."""


def filter_eligible_players(players: List[OptimizerPlayer], settings: OptimizerSettings) -> List[OptimizerPlayer]:
    eligible = []
    for p in players:
        if settings.min_confidence is not None:
            if p.confidence is None or p.confidence < settings.min_confidence:
                continue
        if settings.min_season_pa is not None and p.player_type == "hitter":
            if p.season_sample_size is None or p.season_sample_size < settings.min_season_pa:
                continue
        if settings.max_player_risk is not None:
            if p.risk_score is not None and p.risk_score > settings.max_player_risk:
                continue
        if settings.max_player_ownership is not None:
            if p.projected_ownership is None or p.projected_ownership > settings.max_player_ownership:
                continue
        if settings.min_player_ownership is not None:
            if p.projected_ownership is None or p.projected_ownership < settings.min_player_ownership:
                continue
        eligible.append(p)
    return eligible


def resolve_player_by_name(players: List[OptimizerPlayer], name: str) -> OptimizerPlayer:
    target = normalize_name(name)
    matches = [p for p in players if normalize_name(p.name) == target]
    if not matches:
        raise OptimizerConfigError(f"No active player found matching {name!r}.")
    if len(matches) > 1:
        candidates = ", ".join(f"{m.name} ({m.team})" for m in matches)
        raise OptimizerConfigError(f"{name!r} matches more than one active player: {candidates}. Use a more specific name.")
    return matches[0]


def resolve_settings(
    all_active_players: List[OptimizerPlayer], settings: OptimizerSettings,
) -> Tuple[List[OptimizerPlayer], List[str], Set[str], Dict[str, float], Dict[str, float]]:
    """Validates and resolves every name-based setting to player keys.
    Returns (eligible_players, locked_keys, excluded_keys, max_exposure_by_key, min_exposure_by_key).
    Raises OptimizerConfigError on any contradiction."""
    eligible = filter_eligible_players(all_active_players, settings)
    eligible_keys = {p.key for p in eligible}
    all_by_key = {p.key: p for p in all_active_players}

    locked_keys: List[str] = []
    for name in settings.locks:
        player = resolve_player_by_name(all_active_players, name)
        if player.key not in eligible_keys:
            raise OptimizerConfigError(
                f"Locked player {player.name!r} was filtered out by --min-confidence/--min-season-pa/"
                f"--max-player-risk and cannot be locked into every lineup."
            )
        locked_keys.append(player.key)

    excluded_keys: Set[str] = set()
    for name in settings.excludes:
        excluded_keys.add(resolve_player_by_name(all_active_players, name).key)

    conflict = set(locked_keys) & excluded_keys
    if conflict:
        names = [all_by_key[k].name for k in conflict]
        raise OptimizerConfigError(f"Player(s) both locked and excluded -- contradiction: {names}")

    if len(locked_keys) > DK_ROSTER_SIZE:
        raise OptimizerConfigError(
            f"{len(locked_keys)} players locked, but a DraftKings Classic MLB lineup only has {DK_ROSTER_SIZE} roster spots."
        )

    max_exposure_by_key: Dict[str, float] = {}
    for name, fraction in settings.max_exposure.items():
        if not (0.0 <= fraction <= 1.0):
            raise OptimizerConfigError(f"--max-exposure for {name!r} must be between 0.0 and 1.0, got {fraction}.")
        player = resolve_player_by_name(all_active_players, name)
        if player.key in locked_keys and fraction < 1.0:
            raise OptimizerConfigError(
                f"{player.name!r} is locked (must appear in every lineup) but --max-exposure caps it at "
                f"{fraction:.0%} -- contradiction."
            )
        max_exposure_by_key[player.key] = fraction

    min_exposure_by_key: Dict[str, float] = {}
    for name, fraction in settings.min_exposure.items():
        if not (0.0 <= fraction <= 1.0):
            raise OptimizerConfigError(f"--min-exposure for {name!r} must be between 0.0 and 1.0, got {fraction}.")
        player = resolve_player_by_name(all_active_players, name)
        if player.key in excluded_keys:
            raise OptimizerConfigError(f"{player.name!r} is excluded but also has a --min-exposure target -- contradiction.")
        min_exposure_by_key[player.key] = fraction

    return eligible, locked_keys, excluded_keys, max_exposure_by_key, min_exposure_by_key


def compute_exposure_count_caps(
    max_exposure_by_key: Dict[str, float], default_fraction: float, num_lineups: int, all_keys: List[str],
) -> Dict[str, int]:
    caps = {}
    for key in all_keys:
        fraction = max_exposure_by_key.get(key, default_fraction)
        caps[key] = num_lineups if fraction >= 1.0 else int(fraction * num_lineups)
    return caps


def compute_min_exposure_targets(min_exposure_by_key: Dict[str, float], num_lineups: int) -> Dict[str, int]:
    return {key: math.ceil(fraction * num_lineups) for key, fraction in min_exposure_by_key.items()}


def hitters_by_team(players: List[OptimizerPlayer]) -> Dict[str, List[OptimizerPlayer]]:
    grouping: Dict[str, List[OptimizerPlayer]] = {}
    for p in players:
        if p.player_type == "hitter":
            grouping.setdefault(p.team, []).append(p)
    return grouping


def pitcher_vs_hitter_conflicts(players: List[OptimizerPlayer]) -> Dict[str, List[str]]:
    """pitcher_key -> hitter_keys who face that pitcher (same game, hitter's opponent == pitcher's own team)."""
    pitchers = [p for p in players if p.player_type == "pitcher"]
    hitters = [p for p in players if p.player_type == "hitter"]
    conflicts: Dict[str, List[str]] = {}
    for pitcher in pitchers:
        facing = [h.key for h in hitters if h.game_id and h.game_id == pitcher.game_id and h.opponent == pitcher.team]
        if facing:
            conflicts[pitcher.key] = facing
    return conflicts


def explain_infeasibility(eligible_players: List[OptimizerPlayer], settings: OptimizerSettings) -> List[str]:
    """Best-effort human-readable reasons a solve came back infeasible.
    Not exhaustive (CP-SAT doesn't hand back a minimal conflict set for
    free) -- covers the common, individually-checkable blockers."""
    reasons: List[str] = []

    by_position: Dict[str, List[OptimizerPlayer]] = {slot["slot"]: [] for slot in DK_CLASSIC_ROSTER_SLOTS}
    for p in eligible_players:
        if p.player_type == "pitcher":
            by_position["P"].append(p)
        else:
            for pos in p.dk_positions:
                if pos in by_position:
                    by_position[pos].append(p)

    for slot in DK_CLASSIC_ROSTER_SLOTS:
        available = by_position.get(slot["slot"], [])
        if len(available) < slot["count"]:
            reasons.append(f"Only {len(available)} eligible {slot['slot']} player(s) available (need {slot['count']}).")

    salary_floor = 0
    floor_computable = True
    for slot in DK_CLASSIC_ROSTER_SLOTS:
        available = sorted(by_position.get(slot["slot"], []), key=lambda p: p.salary)
        if len(available) < slot["count"]:
            floor_computable = False
            break
        salary_floor += sum(p.salary for p in available[: slot["count"]])
    if floor_computable and salary_floor > settings.salary_cap:
        reasons.append(
            f"Even the cheapest legal combination costs about ${salary_floor}, "
            f"which exceeds the ${settings.salary_cap} salary cap."
        )

    if settings.stack_size:
        if settings.stack_team:
            team_hitters = [p for p in eligible_players if p.player_type == "hitter" and p.team == settings.stack_team]
            if len(team_hitters) < settings.stack_size:
                reasons.append(
                    f"--stack-team {settings.stack_team} only has {len(team_hitters)} eligible hitter(s) "
                    f"(need {settings.stack_size})."
                )
        else:
            teams = hitters_by_team(eligible_players)
            if not any(len(v) >= settings.stack_size for v in teams.values()):
                reasons.append(f"No team in the eligible pool has {settings.stack_size}+ eligible hitters for the requested stack.")

    if not reasons:
        reasons.append(
            "Position, salary-floor, and stack checks each look individually satisfiable, but no combination of "
            "locks, salary cap, position eligibility, stacking, team limits, and pitcher-vs-hitter rules together is legal."
        )
    return reasons
