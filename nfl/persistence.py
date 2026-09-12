"""NFL M2 -- immutable, timestamped persistence for the canonical NFL
player pool. Mirrors dfs/persistence.py's exact discipline (new file
every build, FileExistsError instead of silent clobber, routed through
research/storage.py's save_json -- the same sport-agnostic primitive
MLB's persistence already uses) but rooted at a sport-scoped path so an
NFL artifact can never collide with or be mistaken for an MLB one:

    dfs_input/nfl/
      YYYY-MM-DD/
        nfl_player_pool_<timestamp>_<draft_group_id>.json

2026-09-11 incident fix: the filename USED to be just
nfl_player_pool_<timestamp>.json -- fine while a slate_date only ever
had one live Classic DraftGroup (true when this was built and tested),
but the instant a date has two or more (confirmed live for
2026-09-13: 153068/153069/153070/153071/151307, all sharing ONE fetch
cycle's timestamp), every DraftGroup after the first collided on the
IDENTICAL path and was refused by raise_if_exists() below --
"Refusing to overwrite existing artifact" -- silently losing 4 of 5
DraftGroups on every single cycle, forever, for that date. The
draft_group_id suffix makes every DraftGroup's file path unique
regardless of how many share a date or a fetch-cycle timestamp.
Backward compatible: list_nfl_player_pools/load_latest_nfl_player_pool
below still recognize the old suffix-less filenames already sitting in
production (see nfl/pool_cache.py's _POOL_TIMESTAMP_RE).

NFL M2 scope: local disk only (LocalArtifactStorage, the default when
OBJECT_STORAGE_* isn't configured) -- no production R2 writes, no
Railway/worker integration, per this milestone's explicit boundary.
"""

import re
from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.models import NflPoolBuildResult

DEFAULT_NFL_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input" / "nfl"

# Matches both the new <timestamp>_<draft_group_id>.json filenames and
# the old, pre-2026-09-11-fix <timestamp>.json-only ones already in
# production -- group(2) is None for an old file.
_POOL_FILENAME_RE = re.compile(r"nfl_player_pool_(\d{8}T\d{6})(?:_(\d+))?\.json$")


def save_nfl_player_pool(result: NflPoolBuildResult, timestamp: str, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT) -> Path:
    path = Path(output_root) / result.slate_date / f"nfl_player_pool_{timestamp}_{result.draft_group_id}.json"
    raise_if_exists(path)
    save_json(path, result.to_dict())
    return path


def list_nfl_player_pools(
    slate_date: str, draft_group_id: Optional[int] = None, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT,
) -> List[Path]:
    """Every saved NFL pool snapshot for a date, oldest first (filenames
    sort chronologically -- mirrors dfs/persistence.py::list_player_pools).
    Pass draft_group_id to scope this to exactly that DraftGroup's own
    files -- REQUIRED for any date with more than one live DraftGroup
    (see this module's own 2026-09-11 incident note): without it, a
    caller can't tell which DraftGroup a given file belongs to, and
    retention pruning would treat every DraftGroup sharing a date as one
    shared pool, evicting one DraftGroup's history to make room for
    another's. Omitting it returns every DraftGroup's files for the
    date, oldest first overall -- only correct for a caller that
    genuinely wants that (there is none left in this codebase; kept
    optional for a future genuine cross-DraftGroup date-level view)."""
    folder = Path(output_root) / slate_date
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_player_pool_", ext=".json")
    if draft_group_id is None:
        return [ARTIFACT_ROOT / key for key in keys]
    matching = []
    for key in keys:
        m = _POOL_FILENAME_RE.search(Path(key).name)
        # An old, suffix-less file (m.group(2) is None) can't be matched
        # to a specific DraftGroup by filename alone -- never assumed to
        # belong to the requested one just because it's the only file
        # present (that was this exact bug's other face: a wrong-
        # DraftGroup file silently answering for the right one).
        if m and m.group(2) is not None and int(m.group(2)) == draft_group_id:
            matching.append(ARTIFACT_ROOT / key)
    return matching


def load_latest_nfl_player_pool(
    slate_date: str, draft_group_id: Optional[int] = None, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT,
) -> Optional[dict]:
    pools = list_nfl_player_pools(slate_date, draft_group_id, output_root)
    if not pools:
        return None
    path = pools[-1]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(path))
