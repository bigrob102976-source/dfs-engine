"""Converts normalized provider-player dicts (as saved by
scripts/fetch_dfs_slate.py) into the same DKSalaryRow shape
dfs/draftkings_parser.py produces from a real CSV -- so
dfs/player_resolver.py, dfs/slate_validation.py, and dfs/player_pool.py
never need to know or care whether a row came from a CSV or a provider.
"""

from typing import Dict, List

from dfs.models import DKSalaryRow


def provider_players_to_dk_rows(players: List[Dict]) -> List[DKSalaryRow]:
    return [
        DKSalaryRow(
            dk_player_id=p["external_player_id"],
            name=p["name"],
            team_abbrev=p["team"],
            dk_positions=list(p.get("position_eligibility") or []),
            salary=p["salary"],
            game_info=p.get("game") or "",
            avg_points_per_game=None,
            roster_position_raw=None,
        )
        for p in players
    ]
