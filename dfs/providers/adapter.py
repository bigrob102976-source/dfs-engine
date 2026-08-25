"""Converts normalized provider-player dicts (as saved by
scripts/fetch_dfs_slate.py) into the same DKSalaryRow shape
dfs/draftkings_parser.py produces from a real CSV -- so
dfs/player_resolver.py, dfs/slate_validation.py, and dfs/player_pool.py
never need to know or care whether a row came from a CSV or a provider.
"""

from typing import Dict, List

from dfs.models import DKSalaryRow


def _split_dk_positions(raw_positions: List[str]) -> List[str]:
    """Optimizer correctness hotfix: some providers (confirmed live for
    dfs/providers/draftkings_unofficial_provider.py) report a multi-
    position-eligible player's position as ONE slash-joined string (e.g.
    "3B/OF") rather than one entry per eligible position. Every OTHER
    dk_positions producer in this project already splits on "/" --
    dfs/draftkings_parser.py's real-CSV path (`position_field.split("/")`)
    and dfs/providers/csv_import_pool_provider.py's CSV-import path both
    do -- so a compound, unsplit string reaching this adapter was a
    silent parity gap between the CSV and provider paths, not a
    deliberate difference. Left unsplit, optimizer/solver.py::
    eligible_for_slot() does an exact-membership check ("3B" in
    dk_positions) that can never match a compound "3B/OF" string, so an
    affected multi-position hitter was silently excluded from EVERY
    roster slot -- never an error, just quietly missing 10-20% of a
    real slate's hitter pool. Splitting here (not in the DK Unofficial
    provider's own merge logic) fixes it at the one shared choke point
    every non-CSV provider already routes through, so any current or
    future provider with the same raw-format quirk is covered too."""
    split: List[str] = []
    for raw in raw_positions:
        for segment in str(raw).split("/"):
            segment = segment.strip()
            if segment and segment not in split:
                split.append(segment)
    return split


def provider_players_to_dk_rows(players: List[Dict]) -> List[DKSalaryRow]:
    return [
        DKSalaryRow(
            dk_player_id=p["external_player_id"],
            name=p["name"],
            team_abbrev=p["team"],
            dk_positions=_split_dk_positions(list(p.get("position_eligibility") or [])),
            salary=p["salary"],
            game_info=p.get("game") or "",
            avg_points_per_game=None,
            roster_position_raw=None,
        )
        for p in players
    ]
