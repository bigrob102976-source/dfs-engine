"""CLI entry point: run Big Money ML shadow inference for a slate date.

    python scripts/run_ml_shadow_inference.py --date YYYY-MM-DD

SHADOW MODE ONLY. Mirrors the non-blocking contract
dashboard/lib/slatePipeline.ts already uses for FantasyPros/AI/Native:
this script always exits 0 for every EXPECTED outcome (no DK pool yet,
no eligible starters, feature parity insufficient, model artifact
missing) and communicates status via a trailing JSON line. Only a
genuinely unexpected crash should ever produce a non-zero exit --
a failed shadow run must never make an entire slate unpublishable.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from big_money_ml.shadow_inference import ShadowInferenceError, run_ml_shadow_inference  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Big Money ML shadow inference for a slate date.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    try:
        document = run_ml_shadow_inference(args.date)
    except ShadowInferenceError as exc:
        print(f"Big Money ML shadow inference stopped: {exc}")
        print(json.dumps({"status": "feature_parity_error", "reason": str(exc), "date": args.date}))
        return
    except Exception as exc:  # noqa: BLE001 -- never take the slate down; report and exit 0
        print(f"Big Money ML shadow inference failed unexpectedly: {exc}")
        print(json.dumps({"status": "error", "reason": str(exc), "date": args.date}))
        return

    print(f"Big Money ML model version: {document.model_version}")
    print(f"Raw DK pitcher rows: {document.raw_dk_pitcher_count}")
    print(f"Starting pitchers: {document.starting_pitcher_count}")
    print(f"ML-eligible pitchers: {document.ml_eligible_pitcher_count}")
    print(f"ML projections generated: {document.ml_projections_generated}")
    print(f"ML projections missing: {document.ml_projections_missing}")

    if document.ml_eligible_pitcher_count == 0:
        status = "no_eligible_pitchers"
    elif document.ml_projections_missing == 0:
        status = "ready"
    elif document.ml_projections_generated > 0:
        status = "partial"
    else:
        status = "no_projections_generated"

    print(json.dumps({
        "status": status, "date": args.date, "model_version": document.model_version,
        "ml_eligible_pitcher_count": document.ml_eligible_pitcher_count,
        "ml_projections_generated": document.ml_projections_generated,
        "ml_projections_missing": document.ml_projections_missing,
    }))


if __name__ == "__main__":
    main()
