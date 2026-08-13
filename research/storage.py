"""Storage stage: write a normalized, validated research package to plain
JSON files on disk. No database, no ORM — one folder per slate date.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from research.models import BatterRecord, Game, PitcherRecord, ResearchMetadata, SlateIndex, Team


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_package(
    output_root: Path,
    slate_date: str,
    games: List[Game],
    teams: List[Team],
    pitchers: List[PitcherRecord],
    batters: List[BatterRecord],
    slate_index: SlateIndex,
    metadata: ResearchMetadata,
) -> Dict[str, str]:
    """Write games.json, teams.json, pitchers.json, batters.json,
    slate.json, and metadata.json under `output_root/slate_date/`.

    Returns a dict of category -> file path written, for the CLI report.
    """
    folder = Path(output_root) / slate_date
    files: Dict[str, str] = {}

    targets = {
        "games": (folder / "games.json", [asdict(g) for g in games]),
        "teams": (folder / "teams.json", [asdict(t) for t in teams]),
        "pitchers": (folder / "pitchers.json", [asdict(p) for p in pitchers]),
        "batters": (folder / "batters.json", [asdict(b) for b in batters]),
        "slate": (folder / "slate.json", slate_index.to_dict()),
        "metadata": (folder / "metadata.json", metadata.to_dict()),
    }

    for name, (path, data) in targets.items():
        save_json(path, data)
        files[name] = str(path)

    return files
