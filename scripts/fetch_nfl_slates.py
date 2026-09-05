"""NFL M15 -- external NFL DraftKings fetch, run on a machine with real
DraftKings network access. Railway's own egress IP is blocked from
reaching DraftKings directly -- the SAME real, already-documented block
MLB's production dashboard hit (see scripts/fetch_all_dfs_slates.py's
docstring). MLB's fix was an external fetch + object-storage-cache-
reuse architecture; this script is that same pattern for NFL, built on
NFL's OWN already-existing modules (draftkings_unofficial/collector.py,
nfl/pool_builder.py, nfl/persistence.py, nfl/pool_cache.py) rather than
MLB's dfs/providers/* abstraction, which NFL doesn't use.

Discovers every real Classic NFL DraftGroup currently live, builds and
persists a canonical pool snapshot for each via the EXISTING
nfl/pool_builder.py::build_pool() + nfl/persistence.py::
save_nfl_player_pool() (built in NFL M2, never wired into a live caller
until this milestone), and persists the discovery list itself via
nfl/pool_cache.py::save_nfl_universe_snapshot() so a caller without
DraftKings access can still populate its slate picker
(scripts/nfl_dashboard_slates.py) and resolve draft_group_id ->
slate_date (nfl/pool_cache.py::resolve_nfl_slate_date(), used by every
other NFL dashboard bridge script).

Intended to run on a schedule (e.g. Windows Task Scheduler, every few
minutes -- comfortably inside nfl/pool_cache.py's 15-minute freshness
window) from a machine with real DraftKings network access, injecting
production storage credentials via `railway run` -- exactly mirroring
how scripts/fetch_all_dfs_slates.py already keeps MLB's production
dashboard supplied. NOT intended to run inside the Railway container
itself.

No CSV/mock/synthetic fallback: every persisted snapshot is a real,
structurally-validated DraftKings pool. A DraftGroup that fails to
build is reported and skipped -- never replaced with fabricated data.

Usage:
    python scripts/fetch_nfl_slates.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from nfl.persistence import save_nfl_player_pool
from nfl.pool_builder import NflPoolBuildError, build_pool
from nfl.pool_cache import save_nfl_universe_snapshot

CLASSIC_GAME_TYPE_ID = 1


def main() -> int:
    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        print(json.dumps({"error": f"DISCOVERY_FAILED: {universe.status} ({universe.error})"}))
        return 1

    slates = []
    for s in universe.slates:
        if s.game_type_id != CLASSIC_GAME_TYPE_ID:
            continue
        slate_date = collector.slate_local_date(s)
        if slate_date is None:
            continue
        slates.append({
            "draft_group_id": s.draft_group_id, "slate_date": slate_date,
            "start_time": s.start_time, "tag": s.tag, "label": s.label,
        })

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    universe_path = None
    try:
        universe_path = save_nfl_universe_snapshot(slates, timestamp)
    except FileExistsError:
        pass  # a snapshot for this exact second already exists -- harmless, per-DraftGroup pools below still proceed

    results = []
    for s in slates:
        try:
            pool = build_pool(s["slate_date"], s["draft_group_id"], sport_code="NFL")
        except NflPoolBuildError as exc:
            results.append({"draft_group_id": s["draft_group_id"], "slate_date": s["slate_date"], "status": "error", "error": str(exc)})
            continue
        try:
            pool_path = save_nfl_player_pool(pool, timestamp)
        except FileExistsError as exc:
            results.append({"draft_group_id": s["draft_group_id"], "slate_date": s["slate_date"], "status": "error", "error": str(exc)})
            continue
        results.append({
            "draft_group_id": s["draft_group_id"], "slate_date": s["slate_date"], "status": "ok",
            "player_count": len(pool.players), "path": str(pool_path),
        })

    print(json.dumps({
        "universe_path": str(universe_path) if universe_path else None,
        "slates_discovered": len(slates), "results": results,
    }))
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
