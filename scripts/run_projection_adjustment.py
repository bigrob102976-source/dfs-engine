"""CLI entry point: run the Big Money Research Adjustment Layer against
the latest external baseline snapshot for a date, using the latest
independent Pitcher/Batter Agent snapshots as the research signal
source. Persists an immutable adjusted-projection snapshot.

    Immutable Baseline Snapshot -> Big Money Research Adjustment Layer
        -> Adjusted Projection Snapshot

    python scripts/run_projection_adjustment.py --date YYYY-MM-DD

Requires a baseline snapshot to already exist for `date` (see
scripts/build_external_projection_baseline.py) and at least one of the
independent pitcher/batter snapshots. Never invents research signals --
a player whose independent snapshot record has no confidence/trend data
simply gets zero adjustment factors and adjusted_projection ==
external_projection.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.adjustment_config import BIG_MONEY_ADJUSTMENT_VERSION  # noqa: E402
from dfs.snapshot_selection import select_snapshot  # noqa: E402
from external_projections.adjustment_engine import build_adjusted_records  # noqa: E402
from external_projections.models import ExternalProjectionPlayer, ProjectionMergeResult  # noqa: E402
from external_projections.persistence import load_latest_baseline_snapshot, save_adjusted_snapshot  # noqa: E402
from external_projections.projection_merge import match_external_to_independent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Big Money Research Adjustment Layer against the latest external baseline snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--provider", default=None, help="Only use a baseline snapshot from this provider name.")
    parser.add_argument("--predictions-root", default="predictions")
    args = parser.parse_args()

    baseline = load_latest_baseline_snapshot(args.date, provider=args.provider)
    if baseline is None:
        print(json.dumps({"status": "no_baseline", "reason": f"No external baseline snapshot found for {args.date}. Run build_external_projection_baseline.py first."}))
        return

    pitcher_snapshot, pitcher_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "pitcher_board")
    batter_snapshot, batter_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "batter_board")
    if pitcher_snapshot is None and batter_snapshot is None:
        print(json.dumps({"status": "no_research", "reason": f"No pitcher or batter snapshot found for {args.date}."}))
        return

    baseline_players = [ExternalProjectionPlayer(**p) for p in baseline["players"]]
    pitcher_ext = [p for p in baseline_players if p.position == "P"]
    hitter_ext = [p for p in baseline_players if p.position != "P"]

    pitcher_records = (pitcher_snapshot or {}).get("pitchers", [])
    hitter_records = (batter_snapshot or {}).get("hitters", [])

    pitcher_merge = match_external_to_independent(pitcher_ext, pitcher_records, "pitcher")
    hitter_merge = match_external_to_independent(hitter_ext, hitter_records, "hitter")
    merge_result = ProjectionMergeResult(
        records=pitcher_merge.records + hitter_merge.records,
        unmatched_external=pitcher_merge.unmatched_external + hitter_merge.unmatched_external,
        unmatched_independent=pitcher_merge.unmatched_independent + hitter_merge.unmatched_independent,
        ambiguous_external=pitcher_merge.ambiguous_external + hitter_merge.ambiguous_external,
    )

    research_by_id = {str(r["player_id"]): r for r in pitcher_records}
    research_by_id.update({str(r["player_id"]): r for r in hitter_records})

    adjusted_records = build_adjusted_records(merge_result, research_by_id)

    generated_at = datetime.now(timezone.utc).isoformat()
    document = {
        "slate_date": args.date,
        "generated_at": generated_at,
        "adjustment_model_version": BIG_MONEY_ADJUSTMENT_VERSION,
        "baseline_provider": baseline.get("provider"),
        "baseline_provider_name": baseline.get("provider_name"),
        "baseline_is_mock": baseline.get("is_mock"),
        "baseline_retrieved_at": baseline.get("retrieved_at"),
        "pitcher_snapshot_path": pitcher_snapshot_path,
        "batter_snapshot_path": batter_snapshot_path,
        "record_count": len(adjusted_records),
        "records": [r.to_dict() for r in adjusted_records],
        "unmatched_external": merge_result.unmatched_external,
        "unmatched_independent": merge_result.unmatched_independent,
        "ambiguous_external": merge_result.ambiguous_external,
    }
    path = save_adjusted_snapshot(document)

    print(f"Adjustment model version: {BIG_MONEY_ADJUSTMENT_VERSION}")
    print(f"Records adjusted: {len(adjusted_records)}")
    print(f"Unmatched external: {len(merge_result.unmatched_external)}")
    print(f"Unmatched independent: {len(merge_result.unmatched_independent)}")
    print(f"\nSaved: {path}")
    print(json.dumps({"status": "ready", "path": str(path), "record_count": len(adjusted_records)}))


if __name__ == "__main__":
    main()
