"""CLI entry point: grade a pregame prediction snapshot against actual
(postgame) results.

    predictions/<date>/pitcher_board_<ts>.json  (pregame, immutable)
        + results/<date>/pitcher_results.json    (postgame, from
          scripts/collect_pitcher_results.py)
        -> evaluation.pitcher_evaluator
        -> printed report + evaluations/<date>/pitcher_evaluation_<ts>.json

This script reads results/ and evaluations/ -- it must NEVER be imported
by, or feed data back into, the pregame Pitcher Agent pipeline. It does
not change any Pitcher Agent weight or threshold; it only measures.

Usage:
    python scripts/evaluate_pitcher_slate.py --date YYYY-MM-DD
    python scripts/evaluate_pitcher_slate.py --date YYYY-MM-DD --snapshot predictions/2026-08-05/pitcher_board_20260805T165500.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.pitcher_evaluator import evaluate_slate
from research.prediction_snapshot import DEFAULT_PREDICTIONS_ROOT, list_snapshots, load_latest_snapshot, load_snapshot, timestamp_tag
from research.storage import save_json

DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"
DEFAULT_EVALUATIONS_ROOT = Path(__file__).resolve().parent.parent / "evaluations"


def _fmt(value, digits=3, none_text="n/a") -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else none_text


def _print_pitcher_row(r) -> str:
    return (
        f"  {r['name']:<24} proj={_fmt(r['projection'],1):<7} actual={_fmt(r['actual_dfs_points'],1):<7} "
        f"err={_fmt(r['error'],1):<7} pred_rk={r['predicted_rank']!s:<4} act_rk={r['actual_rank']!s:<4}"
    )


def _print_report(report) -> None:
    d = report.to_dict()
    sm = d["slate_metrics"]

    print("=" * 70)
    print("PITCHER MODEL EVALUATION")
    print(f"Slate: {d['slate_date']}")
    print(f"Model Version: {d['model_version']}")
    print("=" * 70)
    print()
    print(f"Pitchers Predicted: {d['pitcher_count_predicted']}")
    print(f"Pitchers Evaluated (completed_start only): {sm['pitchers_evaluated']}")
    print(f"Status Breakdown: {d['status_breakdown']}")
    print()
    print(f"MAE: {_fmt(sm['mae'], 2)}")
    print(f"RMSE: {_fmt(sm['rmse'], 2)}")
    print(f"Projection Correlation: {_fmt(sm['projection_correlation'])}")
    print(f"Overall Score Correlation: {_fmt(sm['overall_score_correlation'])}")
    print(f"Top-5 Hit Rate: {_fmt(d['top5_hit_rate'])}")
    print(f"Top-10 Hit Rate: {_fmt(d['top10_hit_rate'])}")
    print(f"Ceiling Hit Rate: {_fmt(sm['ceiling_hit_rate'])}")
    print(f"Floor Miss Rate: {_fmt(sm['floor_miss_rate'])}")
    print()

    print("TOP PREDICTED")
    for r in d["top_predicted"][:10]:
        print(_print_pitcher_row(r))
    print()

    print("TOP ACTUAL")
    for r in d["top_actual"][:10]:
        print(_print_pitcher_row(r))
    print()

    print("BEST CALLS (smallest rank error)")
    for r in d["best_calls"]:
        print(f"  {r['name']:<24} pred_rk={r['predicted_rank']!s:<4} act_rk={r['actual_rank']!s:<4} rank_err={r['rank_error']:+d}")
    print()

    print("WORST CALLS (largest rank error)")
    for r in d["worst_calls"]:
        print(f"  {r['name']:<24} pred_rk={r['predicted_rank']!s:<4} act_rk={r['actual_rank']!s:<4} rank_err={r['rank_error']:+d}")
    print()

    print("BIGGEST POSITIVE SURPRISES (actual - projected)")
    for r in d["biggest_positive_surprises"]:
        print(f"  {r['name']:<24} proj={_fmt(r['projection'],1)} actual={_fmt(r['actual_dfs_points'],1)} diff={r['error']:+.1f}")
    print()

    print("BIGGEST BUSTS (actual - projected)")
    for r in d["biggest_busts"]:
        print(f"  {r['name']:<24} proj={_fmt(r['projection'],1)} actual={_fmt(r['actual_dfs_points'],1)} diff={r['error']:+.1f}")
    print()

    print("TAG PERFORMANCE")
    if d["tag_performance"]:
        for t in d["tag_performance"]:
            print(
                f"  {t['tag']:<28} n={t['count']:<4} avg_proj={_fmt(t['avg_projected_dfs_points'],1):<7} "
                f"avg_actual={_fmt(t['avg_actual_dfs_points'],1):<7} avg_err={_fmt(t['avg_error'],1):<7} "
                f"avg_rank={_fmt(t['avg_actual_rank'],1)}"
            )
    else:
        print("  (no tagged, eligible pitchers this slate)")
    print()

    print("CONFIDENCE CALIBRATION")
    for b in d["confidence_bucket_summary"]:
        print(f"  {b['bucket']:<8} n={b['count']:<4} MAE={_fmt(b['mae'],2):<7} avg_error={_fmt(b['avg_error'],2)}")
    print()

    print("RISK CALIBRATION")
    for b in d["risk_bucket_summary"]:
        print(
            f"  {b['bucket']:<8} n={b['count']:<4} avg_actual={_fmt(b['avg_actual_dfs_points'],2):<8} "
            f"variance={_fmt(b['variance'],2):<8} bust_rate={_fmt(b['bust_rate'])} ceiling_hit_rate={_fmt(b['ceiling_hit_rate'])}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a pregame prediction snapshot against actual results.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--snapshot", default=None, help="Path to a specific prediction snapshot (default: latest for --date)")
    parser.add_argument("--results", default=None, help="Path to pitcher_results.json (default: results/<date>/pitcher_results.json)")
    parser.add_argument("--predictions-root", default=str(DEFAULT_PREDICTIONS_ROOT))
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_EVALUATIONS_ROOT), help="Evaluations output root (default: evaluations)")
    args = parser.parse_args()

    if args.snapshot:
        snapshot = load_snapshot(Path(args.snapshot))
        snapshot_path = args.snapshot
    else:
        snapshot = load_latest_snapshot(args.date, Path(args.predictions_root))
        snapshot_path = str(list_snapshots(args.date, Path(args.predictions_root))[-1])

    results_path = Path(args.results) if args.results else Path(args.results_root) / args.date / "pitcher_results.json"
    if not results_path.exists():
        print(f"No actual results found at {results_path}.")
        print(f"Run: python scripts/collect_pitcher_results.py --date {args.date}")
        return
    with results_path.open("r", encoding="utf-8") as f:
        results_doc = json.load(f)

    report = evaluate_slate(snapshot, results_doc["results"], snapshot_path=snapshot_path)
    _print_report(report)

    eval_path = Path(args.output) / args.date / f"pitcher_evaluation_{timestamp_tag(snapshot['generated_at'])}.json"
    save_json(eval_path, report.to_dict())
    print(f"Evaluation report written to: {eval_path}")


if __name__ == "__main__":
    main()
