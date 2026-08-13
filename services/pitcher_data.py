"""Data-loading boundary for the Pitcher Agent.

This is the only place that knows how pitcher data gets from a source
(today: a local JSON file; later: MLB Stats API / Baseball Savant / a
salary CSV) into the normalized `PitcherInput` model. The agent itself
never reaches out to external sources directly.
"""

import json
from pathlib import Path
from typing import List

from models.pitcher import PitcherInput

DEFAULT_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_pitchers.json"


def load_pitchers_from_json(path: Path = DEFAULT_SAMPLE_PATH) -> List[PitcherInput]:
    """Load and normalize a slate of pitchers from a JSON file.

    Fails loudly (raises) if the file is missing or malformed rather than
    silently returning an empty/partial slate.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pitcher data file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    pitchers = raw.get("pitchers", raw) if isinstance(raw, dict) else raw
    if not isinstance(pitchers, list):
        raise ValueError(f"Expected a list of pitcher records in {path}")

    return [PitcherInput.from_dict(record) for record in pitchers]
