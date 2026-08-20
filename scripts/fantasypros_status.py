"""CLI entry point: prints a single JSON line describing FantasyPros
status for a (date, slate) -- what the admin Slate Operations board
renders. Never prints the API key (this script only ever calls
fantasypros.client.is_configured(), a boolean check).

Reports coverage against the CURRENT DK SLATE'S optimizer-eligible
players (Milestone 30.1's eligibility layer) -- never against every
FantasyPros player MLB-wide, per this milestone's explicit "Big Money
DFS must NOT show every FantasyPros player" instruction.

    python scripts/fantasypros_status.py --date YYYY-MM-DD --slate-id main

Status values:
  NOT_CONFIGURED -- FANTASYPROS_API_KEY is not set.
  NO_SNAPSHOT    -- configured, but no snapshot has been fetched yet for
                    this date (Process/Refresh hasn't run, or every past
                    attempt failed -- see the admin audit log / recent
                    operations for a specific api_error reason from the
                    moment a fetch actually ran; this script only reports
                    persisted, observable state, never a live API call).
  AVAILABLE      -- a snapshot exists and covers every optimizer-eligible
                    player in the given slate's pool.
  PARTIAL        -- a snapshot exists but covers only some (or zero) of
                    the slate's optimizer-eligible players -- expected
                    and normal given FantasyPros' free-tier limits (see
                    fantasypros/client.py's module docstring).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.persistence import load_latest_player_pool  # noqa: E402
from fantasypros import client  # noqa: E402
from fantasypros.persistence import load_latest_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report FantasyPros configuration/snapshot/coverage status for one (date, slate).")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", default=None)
    parser.add_argument("--dfs-input-root", default="dfs_input")
    args = parser.parse_args()

    configured = client.is_configured()
    snapshot = load_latest_snapshot(args.date)

    eligible_count = 0
    matched_eligible_count = 0
    unmatched_eligible_names = []

    if snapshot is not None:
        fp_mlb_ids = {
            p["mlb_player_id"] for p in snapshot.get("players", [])
            if p.get("match_status") == "matched" and p.get("mlb_player_id")
        }
        pool_doc = load_latest_player_pool(args.date, args.slate_id, output_root=args.dfs_input_root)
        if pool_doc is not None:
            for player in pool_doc.get("players", []):
                if player.get("optimizer_eligible"):
                    eligible_count += 1
                    if player.get("mlb_player_id") in fp_mlb_ids:
                        matched_eligible_count += 1
                    else:
                        unmatched_eligible_names.append(player.get("name"))

    if not configured:
        status = "NOT_CONFIGURED"
    elif snapshot is None:
        status = "NO_SNAPSHOT"
    elif eligible_count > 0 and matched_eligible_count == eligible_count:
        status = "AVAILABLE"
    else:
        status = "PARTIAL"

    print(json.dumps({
        "slate_date": args.date,
        "slate_id": args.slate_id,
        "status": status,
        "configured": configured,
        "snapshot_exists": snapshot is not None,
        "retrieved_at": snapshot.get("retrieved_at") if snapshot else None,
        "public_api_limited": snapshot.get("public_api_limited") if snapshot else None,
        "api_tier": snapshot.get("api_tier") if snapshot else None,
        "hitter_count": snapshot.get("hitter_count") if snapshot else None,
        "pitcher_count": snapshot.get("pitcher_count") if snapshot else None,
        "eligible_players": eligible_count,
        "matched_eligible_players": matched_eligible_count,
        "unmatched_eligible_names": unmatched_eligible_names,
    }))


if __name__ == "__main__":
    main()
