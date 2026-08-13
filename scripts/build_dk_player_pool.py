"""CLI entry point: ingest a real DraftKings MLB Classic salary CSV,
match it against our canonical MLB Research Package, join it with the
latest (or explicitly chosen) Pitcher/Batter Agent prediction snapshots,
and save one immutable, reproducible DFS player pool.

    DraftKings CSV
    +
    Research Package
    +
    Pitcher Board / Batter Board (prediction snapshots)
    ->
    DK Player Resolver -> Unified DFS Player Pool -> Roster Validation -> Saved Optimization Input

Usage:
    python scripts/build_dk_player_pool.py --date YYYY-MM-DD --csv data/dk/DKSalaries.csv
    python scripts/build_dk_player_pool.py --date YYYY-MM-DD --csv PATH \
        --pitcher-snapshot predictions/YYYY-MM-DD/pitcher_board_....json \
        --batter-snapshot predictions/YYYY-MM-DD/batter_board_....json

This script does NOT optimize lineups (beyond one deterministic
feasibility smoke test) and does NOT modify the Pitcher/Batter Agents or
any existing prediction snapshot.

As of Milestone 13, this is the MANUAL/CSV fallback path -- the normal
one-click dashboard workflow uses scripts/build_dfs_pool_from_provider.py
instead. Both share their core matching/validation/persistence logic via
dfs/pool_builder.py.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv
from dfs.persistence import save_raw_csv
from dfs.pool_builder import build_pool, print_pool_report, save_pool
from research.prediction_snapshot import timestamp_tag


def _load_crosswalk(path):
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a unified DFS player pool from a real DraftKings salary CSV.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--csv", required=True, help="Path to a DraftKings Classic MLB salary export CSV")
    parser.add_argument("--output", default="research_output", help="Research package root directory")
    parser.add_argument("--predictions-root", default="predictions", help="Prediction snapshot root directory")
    parser.add_argument("--pitcher-snapshot", default=None, help="Explicit pitcher snapshot path (default: latest for --date)")
    parser.add_argument("--batter-snapshot", default=None, help="Explicit batter snapshot path (default: latest for --date)")
    parser.add_argument("--crosswalk", default=None, help="Optional JSON file: {dk_player_id: mlb_player_id}")
    parser.add_argument("--dfs-input-root", default="dfs_input", help="Output root for saved DFS import artifacts")
    args = parser.parse_args()

    print("=" * 70)
    print("DRAFTKINGS SLATE IMPORT")
    print("=" * 70)
    print(f"\nSlate date: {args.date}")
    print(f"Salary file: {args.csv}\n")

    try:
        dk_rows = parse_salary_csv(args.csv)
    except (DraftKingsCSVFormatError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return

    crosswalk = _load_crosswalk(args.crosswalk)
    result = build_pool(
        dk_rows, args.date, args.output, args.predictions_root,
        args.pitcher_snapshot, args.batter_snapshot, crosswalk,
    )
    print()

    print_pool_report(result)

    generated_at = datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(generated_at)
    raw_csv_path = save_raw_csv(args.csv, args.date, ts, output_root=args.dfs_input_root)
    pool_path, report_path = save_pool(
        result, args.date, args.dfs_input_root,
        {"csv_source": str(args.csv), "raw_csv_copy": str(raw_csv_path)},
        generated_at=generated_at,
    )

    print("Files written:")
    print(f"  - {raw_csv_path}")
    print(f"  - {pool_path}")
    print(f"  - {report_path}")


if __name__ == "__main__":
    main()
