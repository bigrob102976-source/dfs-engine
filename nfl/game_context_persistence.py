"""NFL M5 -- immutable, timestamped persistence for NflGameContext
snapshots. Mirrors nfl/persistence.py's (M2) and nfl/projection_
persistence.py's (M4) exact discipline.

    research/nfl/game_context/
      YYYY-MM-DD/
        {draft_group_id}/
          nfl_game_context_<timestamp>.json

Reserved (not built in M5): research/nfl/player_usage/,
research/nfl/injuries/, research/nfl/depth_charts/,
research/nfl/weather/{date}/{draft_group_id}/ -- future sibling
persistence modules for later data categories, kept sport- and
category-isolated the same way this one is. No fetcher for any of them
exists yet.

NFL M5 scope: local disk only -- no production R2 writes.
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.game_context_models import NflGameContext

DEFAULT_GAME_CONTEXT_ROOT = Path(__file__).resolve().parent.parent / "research" / "nfl" / "game_context"


def save_nfl_game_context_snapshot(
    games: List[NflGameContext], slate_date: str, draft_group_id: int, timestamp: str,
    output_root: Path = DEFAULT_GAME_CONTEXT_ROOT,
) -> Path:
    path = Path(output_root) / slate_date / str(draft_group_id) / f"nfl_game_context_{timestamp}.json"
    raise_if_exists(path)
    document = {
        "sport": "NFL",
        "slate_date": slate_date,
        "draft_group_id": draft_group_id,
        "schema_version": "1",
        "games": [g.to_dict() for g in games],
    }
    save_json(path, document)
    return path


def list_nfl_game_context_snapshots(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_GAME_CONTEXT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date / str(draft_group_id)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_game_context_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_nfl_game_context_snapshot(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_GAME_CONTEXT_ROOT) -> Optional[dict]:
    snapshots = list_nfl_game_context_snapshots(slate_date, draft_group_id, output_root)
    if not snapshots:
        return None
    path = snapshots[-1]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(path))
