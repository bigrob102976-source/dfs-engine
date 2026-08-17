"""CLI entry point: collect ACTUAL hitter results for a slate date and
score them with the same DraftKings rules the projection system uses.

    Prediction snapshot (who we predicted)
        -> MLB Stats boxscore (what actually happened -- the SAME cached
           boxscore payload collect_pitcher_results.py already fetches;
           no new network call)
        -> status determination (appeared / scratched / postponed / ...)
        -> actual DraftKings points (reusing config.batter_scoring_config.DK_HITTER_SCORING)
        -> results/<date>/hitter_results.json

Run this AFTER the day's games are final. Never run this before lock --
results/ is never read by any pregame pipeline (native_projections/ included).

Usage:
    python scripts/collect_hitter_results.py --date YYYY-MM-DD
    python scripts/collect_hitter_results.py --date YYYY-MM-DD --snapshot predictions/2026-08-05/batter_board_20260805T165500.json
"""

import argparse
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.dk_actual_scoring import calculate_actual_hitter_dk_points
from evaluation.hitter_results_enrichment import parse_all_hitter_results
from evaluation.results_collector import collect_actual_results
from research.prediction_snapshot import DEFAULT_PREDICTIONS_ROOT, list_snapshots, load_latest_snapshot, load_snapshot
from research.storage import save_json

DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and score actual hitter results for a slate date.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--snapshot", default=None, help="Path to a specific batter prediction snapshot (default: latest for --date)")
    parser.add_argument("--predictions-root", default=str(DEFAULT_PREDICTIONS_ROOT), help="Predictions root directory")
    parser.add_argument("--output", default=str(DEFAULT_RESULTS_ROOT), help="Results output root directory (default: results)")
    args = parser.parse_args()

    if args.snapshot:
        snapshot = load_snapshot(Path(args.snapshot))
        snapshot_path = args.snapshot
    else:
        snapshot = load_latest_snapshot(args.date, Path(args.predictions_root), filename_prefix="batter_board")
        snapshot_path = str(list_snapshots(args.date, Path(args.predictions_root), filename_prefix="batter_board")[-1])

    expected_hitters = snapshot["hitters"]
    print(f"Grading {len(expected_hitters)} predicted hitters from snapshot: {snapshot_path}\n")

    game_ids = [h.get("game_id") for h in expected_hitters]
    raw = collect_actual_results(args.date, game_ids)

    if raw.warnings:
        print(f"Collection notes ({len(raw.warnings)}):")
        for w in raw.warnings:
            print(f"  - {w}")
        print()
    if raw.errors:
        print(f"Collection errors ({len(raw.errors)}):")
        for e in raw.errors:
            print(f"  - {e}")
        print()

    retrieved_at = datetime.now(timezone.utc).isoformat()
    actual_results = parse_all_hitter_results(raw, expected_hitters, retrieved_at)

    records = []
    status_counts = {}
    for result in actual_results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        scoring = calculate_actual_hitter_dk_points(result)
        record = asdict(result)
        record["dfs_points"] = scoring["dfs_points"]
        record["dfs_breakdown"] = scoring["breakdown"]
        records.append(record)

    print("Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print()

    output_doc = {
        "slate_date": args.date,
        "generated_at": retrieved_at,
        "snapshot_path": snapshot_path,
        "snapshot_generated_at": snapshot.get("generated_at"),
        "source_metadata": {"mlb_stats_sources": raw.sources_used},
        "result_count": len(records),
        "results": records,
    }

    results_path = Path(args.output) / args.date / "hitter_results.json"
    save_json(results_path, output_doc)
    print(f"Actual results written to: {results_path}")


if __name__ == "__main__":
    main()
