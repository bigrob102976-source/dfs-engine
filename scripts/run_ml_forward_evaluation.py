"""CLI entry point: forward-evaluate Big Money ML against Native/AI/
FantasyPros/Independent using genuinely pregame-captured projections
and actual (postgame) results.

    python scripts/run_ml_forward_evaluation.py --dates 2026-08-20 2026-08-21 2026-08-22
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.big_money_ml_evaluation import compute_disaster_start_bucket, evaluate_forward_performance  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward-evaluate Big Money ML against other projection sources.")
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--disaster-threshold", type=float, default=2.0)
    args = parser.parse_args()

    performance = evaluate_forward_performance(args.dates)
    disaster = compute_disaster_start_bucket(args.dates, threshold=args.disaster_threshold)

    print(f"Slates requested: {performance['slates_requested']}")
    print(f"Slates with actual results: {performance['slates_with_actual_results']}")
    print(f"Slates with ML pregame data: {performance['slates_with_ml_pregame_data']}")
    print()
    print(f"{'source':<16}{'shared_n':>10}{'mae':>8}{'rmse':>8}{'pearson':>10}{'spearman':>10}{'top5':>8}{'top10':>8}")
    for row in performance["source_metrics"]:
        print(
            f"{row['source']:<16}{row['shared_sample_n']:>10}{row['mae'] if row['mae'] is not None else '--':>8}"
            f"{row['rmse'] if row['rmse'] is not None else '--':>8}{row['pearson'] if row['pearson'] is not None else '--':>10}"
            f"{row['spearman'] if row['spearman'] is not None else '--':>10}{row['avg_top5_hit_rate'] if row['avg_top5_hit_rate'] is not None else '--':>8}"
            f"{row['avg_top10_hit_rate'] if row['avg_top10_hit_rate'] is not None else '--':>8}"
        )
    print()
    print(f"Disaster-start bucket (actual <= {disaster['threshold']}): n={disaster['n']}, bias={disaster['bias']}, mae={disaster['mae']}")

    print(json.dumps({"status": "ok", "performance": performance, "disaster_start_bucket": disaster}, default=str))


if __name__ == "__main__":
    main()
