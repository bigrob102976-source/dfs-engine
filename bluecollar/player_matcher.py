"""Resolves BlueCollar players to this project's canonical MLB player
identity. Reuses dfs/player_resolver.py's exact tiered matching
(crosswalk -> exact name+team -> unique name-only fallback, never
guessing on a collision) instead of building a bespoke matcher --
mirrors fantasypros/matcher.py's own pattern exactly, since BlueCollar
supplies no canonical MLB player ID either (only a locally-derived key,
see external_projections/bluecollar_provider.py).
"""

from typing import List

from bluecollar.models import BlueCollarPlayerProjection
from dfs.models import DKSalaryRow
from dfs.player_resolver import resolve_all
from external_projections.models import ExternalProjectionPlayer

# BlueCollar reports its own DK position string per player (e.g. "P",
# "OF", "1B") -- used directly as the synthetic DK position for matching
# purposes, same discipline as fantasypros/matcher.py's
# _SYNTHETIC_DK_POSITIONS (a position string is only used to build a
# plausible DKSalaryRow for resolve_all(); it never overrides the DK
# pool's own authoritative position/eligibility).
_PITCHER_POSITIONS = {"P", "SP", "RP"}


def _dk_positions_for(position: str) -> List[str]:
    return ["P"] if position.upper() in _PITCHER_POSITIONS else [position.upper()] if position else ["OF"]


def _to_dk_row(player: ExternalProjectionPlayer) -> DKSalaryRow:
    return DKSalaryRow(
        dk_player_id=player.external_player_id,
        name=player.name,
        team_abbrev=player.team,
        dk_positions=_dk_positions_for(player.position),
        salary=player.salary or 0,
        game_info="",
    )


def match_bluecollar_players(players: List[ExternalProjectionPlayer], research_package: dict) -> List[BlueCollarPlayerProjection]:
    """Matches every BlueCollar player against `research_package`
    (games/teams/pitchers/batters -- the same shape
    dfs/pool_builder.py::ensure_research_package produces) and returns
    one BlueCollarPlayerProjection per input player, in the same order.
    raw_projection/usable_projection are populated separately by
    bluecollar/build.py -- this module only resolves identity."""
    if not players:
        return []

    dk_rows = [_to_dk_row(p) for p in players]
    matches = resolve_all(dk_rows, research_package)

    results: List[BlueCollarPlayerProjection] = []
    for player, match in zip(players, matches):
        results.append(
            BlueCollarPlayerProjection(
                bluecollar_local_id=player.external_player_id,
                name=player.name,
                team=player.team,
                position=player.position,
                opponent=player.opponent,
                salary=player.salary,
                raw_projection=player.projection,
                match_status=match.match_status,
                match_confidence=match.match_confidence,
                mlb_player_id=match.mlb_player_id,
                candidate_mlb_ids=list(match.candidate_mlb_ids),
                candidate_names=list(match.candidate_names),
            )
        )
    return results
