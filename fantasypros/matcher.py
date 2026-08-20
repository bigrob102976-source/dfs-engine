"""Resolves FantasyPros players to this project's canonical MLB player
identity. Deliberately reuses dfs/player_resolver.py's exact tiered
matching (crosswalk -> exact name+team -> unique name-only fallback,
never guessing on a collision) instead of building a bespoke FantasyPros
matcher -- mirrors external_projections/csv_import/matcher.py's own
"adapt into a DKSalaryRow, call resolve_player" pattern.

FantasyPros supplies no MLB Stats API player ID (only its own `fpid`/
`player_id`, plus an unrelated `yahooid`) -- team+normalized-name is the
best available signal, exactly the situation dfs/player_resolver.py's
Tier 2/3/4 logic already exists to handle safely.
"""

from typing import List

from dfs.models import DKSalaryRow
from dfs.player_resolver import resolve_all
from fantasypros.models import FantasyProsPlayerProjection, FantasyProsRawPlayer

_SYNTHETIC_DK_POSITIONS = {"pitcher": ["P"], "hitter": ["OF"]}


def _to_dk_row(player: FantasyProsRawPlayer) -> DKSalaryRow:
    return DKSalaryRow(
        dk_player_id=player.fpid,
        name=player.name,
        team_abbrev=player.team_id,
        dk_positions=_SYNTHETIC_DK_POSITIONS[player.player_type],
        salary=0,
        game_info="",
    )


def match_fantasypros_players(players: List[FantasyProsRawPlayer], research_package: dict) -> List[FantasyProsPlayerProjection]:
    """Matches every player against `research_package` (games/teams/
    pitchers/batters -- the same shape dfs/pool_builder.py::ensure_research_package
    produces) and returns one FantasyProsPlayerProjection per input
    player, in the same order, DK-points not yet populated (see
    fantasypros/build.py, which calls fantasypros/scoring.py separately)."""
    if not players:
        return []

    dk_rows = [_to_dk_row(p) for p in players]
    matches = resolve_all(dk_rows, research_package)

    results: List[FantasyProsPlayerProjection] = []
    for player, match in zip(players, matches):
        results.append(
            FantasyProsPlayerProjection(
                fantasypros_id=player.fpid,
                name=player.name,
                team=player.team_id,
                player_type=player.player_type,
                yahoo_id=player.yahoo_id,
                raw_stats=dict(player.stats),
                match_status=match.match_status,
                match_confidence=match.match_confidence,
                mlb_player_id=match.mlb_player_id,
                candidate_mlb_ids=list(match.candidate_mlb_ids),
                candidate_names=list(match.candidate_names),
            )
        )
    return results
