"""Milestone 32.1 -- historical MLB feature warehouse build CLI.

Usage:
    python scripts/build_historical_mlb_warehouse.py --start 2025-06-15 --end 2025-06-17
    python scripts/build_historical_mlb_warehouse.py --start 2024-03-28 --end 2025-09-28 --resume
    python scripts/build_historical_mlb_warehouse.py --start 2024-03-28 --end 2025-09-28 --validate-only

Always prints exactly one line of JSON to stdout summarizing the run.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from historical_mlb import reports
from historical_mlb.quality_gates import QualityGateFailure
from historical_mlb.warehouse_builder import run_build


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/resume the historical MLB feature warehouse (Milestone 32.1).")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    reports.write_feature_manifest()

    t0 = time.time()
    try:
        result = run_build(args.start, args.end, resume=args.resume, force=args.force, validate_only=args.validate_only)
    except QualityGateFailure as exc:
        print(json.dumps({"status": "quality_gate_failed", "violations": exc.findings}))
        sys.exit(1)
        return

    elapsed = round(time.time() - t0, 1)

    # Reload rows from disk for the coverage/quality reports (avoids
    # holding two copies of a potentially-large row set in memory at once).
    import pandas as pd

    from historical_mlb.paths import HITTER_FEATURES_PARQUET, PITCHER_FEATURES_PARQUET

    hitter_rows = pd.read_parquet(HITTER_FEATURES_PARQUET).to_dict("records") if HITTER_FEATURES_PARQUET.exists() else []
    pitcher_rows = pd.read_parquet(PITCHER_FEATURES_PARQUET).to_dict("records") if PITCHER_FEATURES_PARQUET.exists() else []

    reports.write_quality_report(result.get("quality_findings", []))
    coverage = reports.write_coverage_report(hitter_rows, pitcher_rows)
    reports.write_build_report({**result, "elapsed_sec": elapsed, "requested_start": args.start, "requested_end": args.end})

    print(json.dumps({
        "status": "ok", "elapsed_sec": elapsed, "games": result["games"],
        "hitter_rows": result["hitter_rows"], "pitcher_rows": result["pitcher_rows"],
        "unique_hitters": result.get("unique_hitters"), "unique_pitchers": result.get("unique_pitchers"),
        "dates_completed": len(result["dates_completed"]), "failed_dates": result["failed_dates"],
        "quality_findings_count": len(result.get("quality_findings", [])),
    }))


if __name__ == "__main__":
    main()
