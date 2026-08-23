"""Safe, narrow reuse of the M32.1 historical warehouse's player
crosswalk (data/historical/mlb/crosswalks/players.parquet, 1,798 rows as
of this milestone's audit) to backfill handedness on freshly-fetched
roster identities.

ONLY mlb_player_id -> (bat_side, throw_side) is ever read from this
file. `team` is deliberately never read here: the historical crosswalk
records a player's MOST-RECENTLY-OBSERVED team across a ~2-season
window (historical_mlb/player_crosswalk_builder.py's own "most-recent
team wins" semantics), which can easily be stale for a player traded
since (confirmed live in this milestone's own audit: the persisted
Anthony Santander row records "TOR", a team he was not on for most of
the window). CURRENT team must always come from today's live roster
fetch (player_identity/roster_source.py) -- never from history. mlb id
+ handedness are safe to reuse because those never change with a trade.

Bat/throw handedness NEVER changes for a real MLB player, so joining by
mlb_player_id (not name, not team) is unconditionally safe regardless of
how stale the row's OTHER fields are.

Missing pandas, a missing/corrupt file, or any other read failure all
degrade to an empty backfill map (never raise) -- this is enrichment,
never critical path; a live roster refresh must succeed with zero
handedness backfill just as well as with it.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_HISTORICAL_CROSSWALK_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "historical" / "mlb" / "crosswalks" / "players.parquet"
)


def load_historical_handedness(path: Path = DEFAULT_HISTORICAL_CROSSWALK_PATH) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """{mlb_player_id: (bat_side, throw_side)} from the historical
    crosswalk, or {} if the file/pandas isn't available. Rows with no
    mlbam_id are skipped (a synthetic-id historical row has nothing to
    join a live MLB id against)."""
    try:
        import pandas as pd  # local import: this whole package must work fine without pandas installed
    except ImportError:
        return {}

    try:
        df = pd.read_parquet(path)
    except (OSError, ValueError, ImportError):
        return {}

    handedness: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for record in df.to_dict("records"):
        mlbam_id = record.get("mlbam_id")
        if not mlbam_id:
            continue
        bat_side = record.get("bat_side") or None
        throw_side = record.get("throw_side") or None
        if bat_side is None and throw_side is None:
            continue
        handedness[str(mlbam_id)] = (bat_side, throw_side)
    return handedness
