"""NFL M7 -- CLI entrypoint: builds real NFL Vegas game context for one
live DraftKings DraftGroup and reports exactly what happened. Never uses
CSV/mock/synthetic data for the DK slate or the odds fetch.

Usage:
    python scripts/build_nfl_game_context.py <draft_group_id>
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from draftkings_unofficial.collector import slate_local_date
from nfl.game_context_builder import build_nfl_game_context
from nfl.game_context_persistence import save_nfl_game_context_snapshot
from nfl.player_research_join import attach_game_context
from nfl.pool_builder import NflPoolBuildError, build_pool


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def main(draft_group_id: int) -> int:
    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        print(f"DISCOVERY_FAILED: {universe.status} ({universe.error})")
        return 1
    slate = next((s for s in universe.slates if s.draft_group_id == draft_group_id), None)
    if slate is None:
        print(f"DraftGroup {draft_group_id} not found in current NFL universe.")
        return 1
    slate_date = slate_local_date(slate)

    print(f"Building NFL pool for DraftGroup {draft_group_id} (date={slate_date})...")
    try:
        pool = build_pool(slate_date=slate_date, draft_group_id=draft_group_id, sport_code="NFL")
    except NflPoolBuildError as exc:
        print(f"BUILD_POOL_FAILED: {exc}")
        return 1

    print(f"slate_date: {pool.slate_date}")
    print(f"players: {len(pool.players)}")

    result = build_nfl_game_context(pool.players, draft_group_id, pool.slate_date)
    mr = result.match_result

    print(f"\nDK games in slate: {result.dk_game_count}")
    print(f"odds source_provenance: {result.odds_fetch.source_provenance}")
    print(f"provider events fetched: {len(result.odds_fetch.events)}")
    if result.odds_fetch.provider_errors:
        print(f"provider errors: {result.odds_fetch.provider_errors}")
    print(f"matched: {len(mr.matched_dk_game_ids)}")
    print(f"unmatched: {len(mr.unmatched_dk_game_ids)}")
    print(f"ambiguous: {len(mr.ambiguous_dk_game_ids)}")

    for g in mr.games:
        print(
            f"  MATCHED away={g.away_team} home={g.home_team} kickoff={g.game_start_time} "
            f"spread_home={g.spread} total={g.total} home_implied={g.home_implied_total} "
            f"away_implied={g.away_implied_total} provider={g.source}"
        )

    timestamp = _timestamp()
    path = save_nfl_game_context_snapshot(mr.games, pool.slate_date, draft_group_id, timestamp)
    print(f"\npersisted: {path}")

    joined = attach_game_context(pool.players, mr.games)
    by_position = {}
    join_failures = 0
    for jc in joined:
        pos = "DST" if jc.player.is_team_entity else jc.player.position
        by_position.setdefault(pos, {"total": 0, "joined": 0})
        by_position[pos]["total"] += 1
        if jc.game is not None:
            by_position[pos]["joined"] += 1
        else:
            join_failures += 1

    print("\nplayer join by position:")
    for pos, counts in sorted(by_position.items()):
        print(f"  {pos}: {counts['joined']}/{counts['total']} joined to a matched game")
    print(f"join failures (player has no matched game context): {join_failures}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/build_nfl_game_context.py <draft_group_id>")
        sys.exit(2)
    sys.exit(main(int(sys.argv[1])))
