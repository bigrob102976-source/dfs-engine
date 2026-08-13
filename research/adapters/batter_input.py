"""Adapter: Research Package -> BatterInput.

Mirrors research/adapters/pitcher_input.py exactly: reads what
research.engine.build_research_package already wrote to disk and maps
identity only -- no statistics, NO network calls. Statistics are filled
in afterward by research.batter_enrichment / research.statcast_batter_enrichment.

LINEUP-ONLY BY CONSTRUCTION: batters.json is only ever populated for
games whose starting lineup has actually been posted (see
research/normalizer.py's normalize_batters, which skips any game with no
posted lineup entirely). This adapter therefore never has to guess,
project, or manufacture a batting order -- it simply reflects whatever
the Research Engine already confirmed. `missing_lineup_games` exposes
which games on the slate have NO posted lineup yet, so callers can report
that gap instead of silently doing nothing.

IMPORTANT IDENTITY RULE: the MLB player ID (`batters.json`'s
`player_id`) is the canonical identifier carried through onto
`BatterInput.player_id` -- never the name.
"""

import json
from pathlib import Path
from typing import Dict, List

from models.batter import BatterInput


class ResearchPackageNotFoundError(FileNotFoundError):
    """Raised when a slate's research package hasn't been built yet."""


def _load_json_list(path: Path) -> list:
    if not path.exists():
        raise ResearchPackageNotFoundError(f"Research package file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_research_package(output_root, slate_date: str) -> Dict[str, list]:
    """Load the raw games/teams/batters records a research package
    already wrote to `output_root/slate_date/`."""
    folder = Path(output_root) / slate_date
    return {
        "games": _load_json_list(folder / "games.json"),
        "teams": _load_json_list(folder / "teams.json"),
        "batters": _load_json_list(folder / "batters.json"),
    }


def build_batter_inputs(package: Dict[str, list]) -> List[BatterInput]:
    """Map research-package starting-lineup batter records into
    BatterInput objects. Every statistical field starts unset (None).
    Salary always stays None: no DFS salary source exists yet, and one
    is never invented."""
    games_by_id = {g["game_id"]: g for g in package["games"]}

    batter_inputs: List[BatterInput] = []
    for record in package["batters"]:
        game = games_by_id.get(record.get("game_id"))

        batter_inputs.append(BatterInput(
            player_id=str(record["player_id"]),  # MLB ID: canonical identity, never the name
            name=record["name"],
            team=record["team_abbr"],
            opponent=record["opponent_abbr"],
            game_id=record.get("game_id"),
            venue_name=game.get("venue_name") if game else None,
            batting_hand=record.get("bats"),  # almost always None at this stage; see research.batter_enrichment.apply_bios_to_batter_inputs
            batting_order=record.get("batting_order"),
            position=record.get("position"),
            salary=None,
        ))
    return batter_inputs


def missing_lineup_games(package: Dict[str, list]) -> List[dict]:
    """Games on the slate with NO posted starting lineup yet -- i.e. no
    batters.json entries reference that game_id at all. Reported, never
    silently skipped."""
    games_with_lineups = {b["game_id"] for b in package["batters"]}
    return [g for g in package["games"] if g["game_id"] not in games_with_lineups]
