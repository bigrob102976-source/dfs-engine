"""Adapter: Research Package -> PitcherInput.

Reads the games.json/teams.json/pitchers.json a research package already
wrote to disk (research.engine.build_research_package) and maps each
probable-pitcher record into the existing `PitcherInput` model the
Pitcher Agent already knows how to score.

This module resolves IDENTITY only (who's pitching, for which team,
against which team, in which game, at which venue) -- no statistics, no
network calls. Season/recent/opponent statistics are filled in
afterward by research.enrichment. Keeping these separate means the
identity mapping can be tested with a couple of small fixture files and
never has to touch the network.

IMPORTANT IDENTITY RULE: the MLB player ID (`pitchers.json`'s
`player_id`) is the canonical identifier carried through onto
`PitcherInput.player_id`. Pitchers are never keyed or matched by name --
names can change, be abbreviated inconsistently, or collide between two
different players.
"""

import json
from pathlib import Path
from typing import Dict, List

from models.pitcher import Availability, PitcherInput


class ResearchPackageNotFoundError(FileNotFoundError):
    """Raised when a slate's research package hasn't been built yet."""


def _load_json_list(path: Path) -> list:
    if not path.exists():
        raise ResearchPackageNotFoundError(f"Research package file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_research_package(output_root, slate_date: str) -> Dict[str, list]:
    """Load the raw games/teams/pitchers records a research package
    already wrote to `output_root/slate_date/`. Raises
    ResearchPackageNotFoundError (not a bare crash) if the package
    doesn't exist yet, so callers can give the user an actionable
    message."""
    folder = Path(output_root) / slate_date
    return {
        "games": _load_json_list(folder / "games.json"),
        "teams": _load_json_list(folder / "teams.json"),
        "pitchers": _load_json_list(folder / "pitchers.json"),
    }


def build_pitcher_inputs(package: Dict[str, list]) -> List[PitcherInput]:
    """Map research-package pitcher identity records into PitcherInput
    objects.

    Every statistical field starts unset (None) -- this adapter only
    resolves identity. Salary always stays None: no DFS salary source
    exists in the Research Engine yet, and one is never invented.
    """
    games_by_id = {g["game_id"]: g for g in package["games"]}

    pitcher_inputs: List[PitcherInput] = []
    for record in package["pitchers"]:
        game = games_by_id.get(record.get("game_id"))
        status = record.get("status")

        pitcher_inputs.append(PitcherInput(
            player_id=str(record["player_id"]),  # MLB ID: canonical identity, never the name
            name=record["name"],
            team=record["team_abbr"],
            opponent=record["opponent_abbr"],
            salary=None,
            throwing_hand=record.get("throws"),
            game_id=record.get("game_id"),
            venue_name=game.get("venue_name") if game else None,
            availability=Availability(
                # "probable"/"confirmed" are the only statuses this
                # milestone's collector produces; either means the MLB
                # Stats API currently expects this pitcher to start.
                confirmed_starter=status in ("probable", "confirmed") if status else None,
            ),
        ))
    return pitcher_inputs
