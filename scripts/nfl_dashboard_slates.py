"""NFL UI M1 -- real DraftKings NFL Classic slate discovery for the
dashboard's slate selector. Never returns Showdown/Best Ball/Madden
DraftGroups -- Classic only (game_type_id == 1, confirmed real via
draftkings_unofficial/structural_validation.py).

Usage:
    python scripts/nfl_dashboard_slates.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from nfl.pool_cache import load_fresh_cached_universe

CLASSIC_GAME_TYPE_ID = 1


def main() -> int:
    cached = load_fresh_cached_universe()
    if cached is not None:
        print(json.dumps({"slates": cached}))
        return 0

    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        print(json.dumps({"error": f"DISCOVERY_FAILED: {universe.status} ({universe.error})"}))
        return 1

    slates = []
    for s in universe.slates:
        if s.game_type_id != CLASSIC_GAME_TYPE_ID:
            continue
        slates.append({
            "draft_group_id": s.draft_group_id,
            "slate_date": collector.slate_local_date(s),
            "start_time": s.start_time,
            "tag": s.tag,
            "label": s.label,
        })

    print(json.dumps({"slates": slates}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
