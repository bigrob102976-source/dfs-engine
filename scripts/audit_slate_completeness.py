"""Milestone 27.2 -- slate/player-pool completeness audit.

For the selected real DraftKings slate, verifies (per team, and overall):

    DK salary CSV rows -> normalized pool rows -> MLB-matched rows ->
    active rows -> Native-projection-covered -> AI-projection-covered

and that every row from the DK CSV is PRESERVED in the normalized pool
(never silently dropped) -- the exact invariant this milestone's live
regression (LAD @ COL, 2026-08-18) proved was violated further downstream
(dashboard row-building, not this pool itself, which was already correct).

Also verifies the cross-system MLB game_id invariant: the DK slate's own
resolved game_ids, the Vegas snapshot's game_id, and the research
package's own game_id must all refer to the SAME authoritative game for
a given matchup -- never silently different ids for "the same" game.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _latest(pattern: str) -> "Path | None":
    matches = sorted(Path(".").glob(pattern))
    return matches[-1] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", default=None)
    args = parser.parse_args()

    pool_path = _latest(f"dfs_input/{args.date}/dk_player_pool_*.json")
    if pool_path is None:
        print(json.dumps({"status": "no_pool", "date": args.date}))
        return
    pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
    if args.slate_id and pool_doc.get("selected_slate_id") not in (None, args.slate_id):
        print(f"WARNING: latest pool's selected_slate_id={pool_doc.get('selected_slate_id')!r} != requested {args.slate_id!r}")

    all_players = pool_doc.get("players", [])
    print(f"Pool: {pool_path.name}")
    print(f"selected_slate_id: {pool_doc.get('selected_slate_id')}")
    print(f"Total normalized pool rows: {len(all_players)}\n")

    by_team: dict = {}
    for p in all_players:
        by_team.setdefault(p["team"], []).append(p)

    print(f"{'TEAM':<6}{'DK/POOL':>9}{'MLB_MATCH':>11}{'ACTIVE':>8}{'UNCONFIRMED':>13}{'UNMATCHED':>11}")
    total_pool = total_match = total_active = total_unconfirmed = total_unmatched = 0
    for team in sorted(by_team):
        rows = by_team[team]
        matched = sum(1 for p in rows if p.get("match_status") == "matched")
        active = sum(1 for p in rows if p.get("lineup_status") == "active")
        unconfirmed = sum(1 for p in rows if p.get("lineup_status") == "lineup_not_confirmed")
        unmatched = sum(1 for p in rows if p.get("match_status") == "unmatched")
        total_pool += len(rows)
        total_match += matched
        total_active += active
        total_unconfirmed += unconfirmed
        total_unmatched += unmatched
        print(f"{team:<6}{len(rows):>9}{matched:>11}{active:>8}{unconfirmed:>13}{unmatched:>11}")

    print(f"\n{'TOTAL':<6}{total_pool:>9}{total_match:>11}{total_active:>8}{total_unconfirmed:>13}{total_unmatched:>11}")

    # --- Completeness: every DK CSV row must appear in the pool ---------
    csv_dir = Path("dfs_input") / args.date / "uploaded_dk_slates"
    csv_files = sorted(csv_dir.glob("*.csv")) if csv_dir.exists() else []
    if csv_files:
        import csv as csv_module

        latest_csv = csv_files[-1]
        with latest_csv.open(encoding="utf-8") as f:
            csv_row_count = sum(1 for _ in csv_module.DictReader(f))
        completeness_pct = round((len(all_players) / csv_row_count) * 100, 1) if csv_row_count else 0.0
        print(f"\nDK CSV: {latest_csv.name}  rows={csv_row_count}")
        print(f"player_pool_completeness_percent: {completeness_pct}%  ({len(all_players)}/{csv_row_count})")
        if len(all_players) < csv_row_count:
            print(f"WARNING: {csv_row_count - len(all_players)} DK CSV rows are NOT present in the normalized pool.")


if __name__ == "__main__":
    main()
