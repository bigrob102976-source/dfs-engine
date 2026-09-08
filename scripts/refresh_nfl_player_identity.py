"""NFL M17 -- CLI entry point: refresh the DraftKings<->GSIS identity
crosswalk (historical_nfl/identity_persistence.py) for every real,
currently-live NFL Classic player.

ROOT CAUSE this fixes (M17 Phase 10 audit, 2026-09-07): the tiered
name/team matcher (historical_nfl/identity_matching.py::resolve_identity)
and the crosswalk persistence layer (historical_nfl/identity_persistence.py)
were both fully implemented and unit-tested, but NOTHING in scripts/ ever
called them together and saved the result -- unlike MLB, which has this
exact script's counterpart (scripts/refresh_player_identity.py) wired
into its daily pipeline. scripts/nfl_dashboard_data.py (the real
dashboard-serving script) only ever READS the persisted crosswalk via
load_crosswalk(), which gracefully returns {} when no version has ever
been saved -- which was always true. That is why only DST rows (team-
abbreviation identity, no crosswalk needed) ever resolved, and why
projection/ownership coverage was 0% for every skill position on every
real Classic slate (live-reproduced on two different real DraftGroups
this same audit: 32/817 and 24/744 resolved, both exactly the DST count).

WHY SEASON 2025, NOT 2026: nflreadpy's own get_current_season() (season
logic: "current year after the Thursday following Labor Day") correctly
still returns 2025 for another few days as of this fix -- Labor Day 2026
is 2026-09-07 and the season doesn't roll to 2026 until 2026-09-10. This
is nflverse's own real, documented convention, not a bug -- passing
season=2026 to fetch_rosters() raises ValueError from nflreadpy itself.
Using season=2025 (the most recent real, available roster data) still
correctly resolves the overwhelming majority of real players via
identity_matching.py's own Tier 3 cross-team fallback (built specifically
for offseason team changes) -- a genuine 2026 rookie who never appeared
on a 2025 roster is honestly left STATUS_UNMATCHED, never fabricated.
This script should simply be re-run once nflreadpy accepts season=2026
(no code change needed -- see --season below).

Discovers the real live NFL Classic universe the same way
scripts/fetch_nfl_slates.py already does (draftkings_unofficial.collector,
filtered to CLASSIC_GAME_TYPE_ID) rather than reinventing discovery, and
unions every real player across every currently-live Classic DraftGroup
to maximize identity coverage for "every game on the selected slate"
(M17 Phase 1's requirement) -- not just one DraftGroup.

No mock/synthetic/CSV fallback of any kind: every row resolved here
came from a real, live DraftKings draftables response and a real
nflverse roster snapshot. A player this can't confidently match is left
genuinely unresolved (STATUS_UNMATCHED/STATUS_AMBIGUOUS/
STATUS_REVIEW_REQUIRED), never guessed.

Same external-network requirement as scripts/fetch_nfl_slates.py --
Railway's own egress IP cannot reach DraftKings directly; run this from
a machine with real network access (this repo's own dev machine, or
wherever fetch_nfl_slates.py already runs), never inside the Railway
container itself.

Usage:
    python scripts/refresh_nfl_player_identity.py
    python scripts/refresh_nfl_player_identity.py --season 2025
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402

from draftkings_unofficial import collector  # noqa: E402
from historical_nfl.identity_models import CrosswalkConflictError  # noqa: E402
from historical_nfl.identity_persistence import load_crosswalk, merge_crosswalk, save_crosswalk  # noqa: E402
from historical_nfl.identity_resolve import (  # noqa: E402
    build_offense_crosswalk_rows,
    resolve_dst_pool,
    resolve_offense_pool,
    summarize_by_position,
)
from historical_nfl.nflverse_client import NflverseUnavailableError, fetch_rosters  # noqa: E402
from nfl.pool_builder import NflPoolBuildError, build_pool  # noqa: E402

CLASSIC_GAME_TYPE_ID = 1


def _discover_classic_players() -> list:
    """Real live NFL Classic players, unioned across every currently-
    live Classic DraftGroup -- same discovery + build_pool() call
    scripts/fetch_nfl_slates.py already uses, never reinvented. Returns
    a de-duplicated (by draftkings_player_id) list of nfl.models.NflPlayer."""
    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        raise RuntimeError(f"DISCOVERY_FAILED: {universe.status} ({universe.error})")

    by_id = {}
    slate_errors = []
    for s in universe.slates:
        if s.game_type_id != CLASSIC_GAME_TYPE_ID:
            continue
        slate_date = collector.slate_local_date(s)
        if slate_date is None:
            continue
        try:
            pool = build_pool(slate_date, s.draft_group_id, sport_code="NFL")
        except NflPoolBuildError as exc:
            slate_errors.append({"draft_group_id": s.draft_group_id, "error": str(exc)})
            continue
        for p in pool.players:
            by_id[p.draftkings_player_id] = p

    return list(by_id.values()), slate_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the real DraftKings<->GSIS NFL identity crosswalk.")
    parser.add_argument("--season", type=int, default=2025, help="nflverse season to match against (see module docstring for why 2025).")
    args = parser.parse_args()

    print("=" * 70)
    print("NFL PLAYER IDENTITY REFRESH")
    print("=" * 70)

    generated_at = datetime.now(timezone.utc).isoformat()

    dk_players, slate_errors = _discover_classic_players()
    print(f"Real live Classic players discovered (union across all live DraftGroups): {len(dk_players)}")
    if slate_errors:
        print(f"DraftGroups that failed to build (skipped, never faked): {json.dumps(slate_errors)}")

    try:
        roster_df, roster_fetched_at, roster_provenance = fetch_rosters(args.season, week=None)
    except NflverseUnavailableError as exc:
        print(json.dumps({"error": f"NFLVERSE_ROSTER_FETCH_FAILED: {exc}"}))
        return 1
    roster_rows = roster_df.to_dicts()
    print(f"Real nflverse roster rows (season={args.season}, all weeks): {len(roster_rows)} ({roster_provenance})")

    existing_crosswalk = load_crosswalk()
    print(f"Existing crosswalk size before this refresh: {len(existing_crosswalk)}")

    offense_players = [p for p in dk_players if not p.is_team_entity]
    dst_players = [p for p in dk_players if p.is_team_entity]

    match_results = resolve_offense_pool(offense_players, existing_crosswalk, roster_rows)
    offense_rows = build_offense_crosswalk_rows(match_results, existing_crosswalk)
    dst_rows = resolve_dst_pool(dst_players, existing_crosswalk)

    dk_by_id = {p.draftkings_player_id: p for p in offense_players}
    summary = summarize_by_position(match_results, dk_by_id)
    print("Match-tier summary by position (offense only -- DST is always 100% via team identity):")
    print(json.dumps(summary, indent=2))

    try:
        merged = merge_crosswalk(existing_crosswalk, offense_rows + dst_rows)
    except CrosswalkConflictError as exc:
        print(json.dumps({"error": f"CROSSWALK_CONFLICT: {exc}"}))
        return 1

    saved_path = save_crosswalk(merged, generated_at)

    total_offense = len(offense_players)
    matched_offense = sum(1 for r in offense_rows if r.gsis_id)
    print(f"\nOffense identity resolved this refresh: {matched_offense}/{total_offense}")
    print(f"DST identity resolved this refresh: {len(dst_rows)}/{len(dst_players)}")
    print(f"Crosswalk size after merge: {len(merged)}")
    print(f"Saved: {saved_path}")
    print(json.dumps({
        "generated_at": generated_at, "dk_players_discovered": len(dk_players), "slate_errors": slate_errors,
        "roster_season": args.season, "roster_rows": len(roster_rows),
        "offense_resolved": matched_offense, "offense_total": total_offense,
        "dst_resolved": len(dst_rows), "dst_total": len(dst_players),
        "crosswalk_size_after": len(merged), "saved_path": str(saved_path),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
