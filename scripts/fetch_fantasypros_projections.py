"""CLI entry point: fetch today's FantasyPros MLB daily projections
(hitters + pitchers), convert to DraftKings fantasy points, match to
this project's canonical MLB player identity, and save an immutable
snapshot.

Usage:
    python scripts/fetch_fantasypros_projections.py --date YYYY-MM-DD

FantasyPros is OPTIONAL and this script never fails the caller's
pipeline: every outcome (not configured, no research package yet, API
error, or success) exits 0 and prints a final JSON status line, mirroring
scripts/run_projection_adjustment.py's own "best-effort, never blocks the
slate" convention. Only a genuinely unexpected exception (a real bug)
would produce a non-zero exit.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasypros.build import STATUS_API_ERROR, STATUS_NOT_CONFIGURED, STATUS_NO_RESEARCH, STATUS_READY, build_fantasypros_snapshot
from fantasypros.persistence import save_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch FantasyPros MLB daily projections and save a snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="research_output", help="Research package root directory")
    args = parser.parse_args()

    print("=" * 70)
    print("FANTASYPROS PROJECTIONS")
    print("=" * 70)

    result = build_fantasypros_snapshot(args.date, args.output)

    if result["status"] == STATUS_NOT_CONFIGURED:
        print("\nFANTASYPROS: NOT CONFIGURED (FANTASYPROS_API_KEY is not set -- this is optional, skipping).")
        print(json.dumps({"status": "not_configured"}))
        return

    if result["status"] == STATUS_NO_RESEARCH:
        print(f"\nFANTASYPROS: SKIPPED -- {result['error']}")
        print(json.dumps({"status": "no_research", "reason": result["error"]}))
        return

    if result["status"] == STATUS_API_ERROR:
        print(f"\nFANTASYPROS: API ERROR -- {result['error']}")
        print(json.dumps({"status": "api_error", "reason": result["error"]}))
        return

    assert result["status"] == STATUS_READY
    snapshot = result["snapshot"]
    path = save_snapshot(snapshot)

    print(f"Hitters returned: {snapshot.hitter_count} (matched: {snapshot.hitters_matched})")
    print(f"Pitchers returned: {snapshot.pitcher_count} (matched: {snapshot.pitchers_matched})")
    print(f"Public API limited: {snapshot.public_api_limited} (tier: {snapshot.api_tier})")
    print(f"\nSaved: {path}")
    print(json.dumps({
        "status": "ready", "path": str(path),
        "hitter_count": snapshot.hitter_count, "pitcher_count": snapshot.pitcher_count,
        "hitters_matched": snapshot.hitters_matched, "pitchers_matched": snapshot.pitchers_matched,
        "public_api_limited": snapshot.public_api_limited,
    }))


if __name__ == "__main__":
    main()
