"""CLI entry point: refresh canonical MLB player identity for every team
playing on a given date, independent of starting-lineup confirmation --
see player_identity/refresh.py's module docstring for the full
architecture.

Intended pipeline position (per this milestone): run this AFTER the
day's schedule/teams are known (research_output/<date>/teams.json,
games.json -- both schedule-derived) but it does NOT need to wait for
lineup-dependent pitcher/batter research to run first.

Usage:
    python scripts/refresh_player_identity.py --date YYYY-MM-DD

Always exits 0 and prints a final JSON status line -- a missing
schedule or a failed roster fetch for some teams degrades gracefully
(see refresh_identity()'s own docstring), never blocks the caller's
pipeline. Only a genuinely unexpected exception (a real bug) would
produce a non-zero exit.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from player_identity.refresh import refresh_identity  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh canonical MLB player identity for every team playing on a given date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--research-output-root", default="research_output")
    args = parser.parse_args()

    print("=" * 70)
    print("PLAYER IDENTITY REFRESH")
    print("=" * 70)

    result = refresh_identity(args.date, research_output_root=args.research_output_root)

    print(f"Slate date: {result.slate_date}")
    print(f"Teams (schedule): {result.teams_total}")
    print(f"Teams fetched: {result.teams_fetched}")
    if result.teams_failed:
        print(f"Teams FAILED to fetch: {', '.join(result.teams_failed)}")
    print(f"Players seen this refresh: {result.players_seen_this_refresh}")
    print(f"Crosswalk size after merge: {result.crosswalk_size_after}")
    print(f"Historical handedness backfill available: {result.historical_backfill_available} "
          f"(applied to {result.historical_backfill_applied_count} players)")
    print(f"\nSnapshot: {result.snapshot_path}")
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
