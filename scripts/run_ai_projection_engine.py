"""CLI entry point: run the AI Projection Engine for a slate date.

    Independent Pitcher/Batter Snapshots + Game Environment + Ownership
    + Adjusted Projection Snapshot (all optional except the two board
    snapshots) -> AI Projection Engine -> AI Projection Snapshot

    python scripts/run_ai_projection_engine.py --date YYYY-MM-DD

Requires at least one of the independent pitcher/batter snapshots (the
Independent Projection is the baseline every AI Projection starts from).
Every other input -- Game Environment, Ownership, the latest Adjusted
Projection snapshot, and the DK player pool (for salary/AI Value Score)
-- is optional; a missing one just means fewer signals fire, never a
hard failure. Never invents a signal -- a player with no upstream data
for a category simply has one fewer entry in their signal breakdown.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.projection_engine_config import AI_PROJECTION_ENGINE_VERSION  # noqa: E402
from dfs.snapshot_selection import select_snapshot  # noqa: E402
from projection_engine.persistence import (  # noqa: E402
    load_latest_adjusted,
    load_latest_dfs_pool,
    load_latest_environment,
    load_latest_ownership,
    save_ai_projection_snapshot,
)
from projection_engine.scoring import build_ai_projection_document, build_ai_projection_slate  # noqa: E402
from projection_engine.validator import validate_ai_projection_slate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI Projection Engine for a slate date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--predictions-root", default="predictions")
    args = parser.parse_args()

    pitcher_snapshot, pitcher_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "pitcher_board")
    batter_snapshot, batter_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "batter_board")
    if pitcher_snapshot is None and batter_snapshot is None:
        print(json.dumps({"status": "no_research", "reason": f"No pitcher or batter snapshot found for {args.date}. Run the Pitcher/Batter Agent first."}))
        return

    environment_report = load_latest_environment(args.date)
    ownership_snapshot = load_latest_ownership(args.date)
    adjusted_snapshot = load_latest_adjusted(args.date)
    pool_doc = load_latest_dfs_pool(args.date)

    records, skip_warnings = build_ai_projection_slate(
        pitcher_snapshot=pitcher_snapshot or {"pitchers": []},
        batter_snapshot=batter_snapshot or {"hitters": []},
        environment_report=environment_report,
        ownership_snapshot=ownership_snapshot,
        adjusted_snapshot=adjusted_snapshot,
        pool_doc=pool_doc,
    )

    valid_records, validation_warnings = validate_ai_projection_slate(records)
    warnings = skip_warnings + validation_warnings

    generated_at = datetime.now(timezone.utc).isoformat()
    document = build_ai_projection_document(
        slate_date=args.date,
        records=valid_records,
        warnings=warnings,
        pitcher_snapshot_path=pitcher_snapshot_path,
        batter_snapshot_path=batter_snapshot_path,
        generated_at=generated_at,
    )
    document["environment_report_present"] = environment_report is not None
    document["ownership_snapshot_present"] = ownership_snapshot is not None
    document["adjusted_snapshot_present"] = adjusted_snapshot is not None
    document["dfs_pool_present"] = pool_doc is not None

    path = save_ai_projection_snapshot(document)

    if valid_records:
        deltas = [r.total_adjustment for r in valid_records]
        avg_adjustment = sum(deltas) / len(deltas)
        biggest_upgrade = max(valid_records, key=lambda r: r.total_adjustment)
        biggest_downgrade = min(valid_records, key=lambda r: r.total_adjustment)
    else:
        avg_adjustment = 0.0
        biggest_upgrade = biggest_downgrade = None

    print(f"AI Projection Engine version: {AI_PROJECTION_ENGINE_VERSION}")
    print(f"Players scored: {len(valid_records)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Average AI adjustment: {avg_adjustment:+.3f}")
    if biggest_upgrade is not None:
        print(f"Largest upgrade: {biggest_upgrade.name} ({biggest_upgrade.total_adjustment:+.2f})")
    if biggest_downgrade is not None:
        print(f"Largest downgrade: {biggest_downgrade.name} ({biggest_downgrade.total_adjustment:+.2f})")
    print(f"\nSaved: {path}")
    print(json.dumps({"status": "ready", "path": str(path), "player_count": len(valid_records), "warning_count": len(warnings)}))


if __name__ == "__main__":
    main()
