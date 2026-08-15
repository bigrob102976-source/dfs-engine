"""CLI entry point: compare every available pregame projection source
(Independent / External / Adjusted / AI) against actual postgame
results for a slate date.

    results/<date>/pitcher_results.json  (postgame, from
        scripts/collect_pitcher_results.py)
    + predictions/<date>/pitcher_board_<ts>.json           (Independent)
    + adjusted_projection_snapshots/<date>/adjusted_<ts>.json (External + Adjusted)
    + ai_projection_snapshots/<date>/ai_projection_<ts>.json  (AI)
        -> evaluation.projection_source_comparison
        -> printed report + evaluations/<date>/projection_source_comparison_<ts>.json

Pitcher-only, same as scripts/evaluate_pitcher_slate.py -- there is no
hitter actual-results source in this codebase yet. Any source missing
for this date is simply omitted from the comparison, never faked.

Usage:
    python scripts/run_projection_source_comparison.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.projection_source_comparison import compare_projection_sources  # noqa: E402
from evaluation.projection_source_loader import build_pitcher_projection_sources, load_actual_pitcher_points  # noqa: E402
from research.prediction_snapshot import timestamp_tag  # noqa: E402
from research.storage import save_json  # noqa: E402

DEFAULT_EVALUATIONS_ROOT = Path(__file__).resolve().parent.parent / "evaluations"


def _fmt(value, digits=3, none_text="n/a") -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else none_text


def _print_report(metrics, improvement) -> None:
    print("=" * 70)
    print("AI PROJECTION PERFORMANCE")
    print("=" * 70)
    print()
    for m in metrics:
        print(f"  {m.source:<12} n={m.n:<4} MAE={_fmt(m.mae, 2):<7} RMSE={_fmt(m.rmse, 2):<7} corr={_fmt(m.correlation):<7} "
              f"rank_corr={_fmt(m.rank_correlation):<7} top5={_fmt(m.top5_hit_rate):<7} top10={_fmt(m.top10_hit_rate)}")
    print()
    if improvement is not None:
        print(f"AI vs Independent MAE improvement: {improvement:+.1f}%")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare every available projection source against actual postgame results.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--output", default=str(DEFAULT_EVALUATIONS_ROOT), help="Evaluations output root (default: evaluations)")
    args = parser.parse_args()

    actual_by_id = load_actual_pitcher_points(args.date)
    if not actual_by_id:
        print(f"No actual results found for {args.date}.")
        print(f"Run: python scripts/collect_pitcher_results.py --date {args.date}")
        return

    sources = build_pitcher_projection_sources(args.date)
    if not sources:
        print(f"No projection sources (independent/external/adjusted/ai) found for {args.date}.")
        return

    metrics = compare_projection_sources(sources, actual_by_id)

    independent_mae = next((m.mae for m in metrics if m.source == "independent"), None)
    ai_mae = next((m.mae for m in metrics if m.source == "ai"), None)
    improvement = round((independent_mae - ai_mae) / independent_mae * 100.0, 1) if independent_mae and ai_mae is not None else None

    _print_report(metrics, improvement)

    generated_at = datetime.now(timezone.utc).isoformat()
    document = {
        "slate_date": args.date,
        "generated_at": generated_at,
        "actual_result_count": len(actual_by_id),
        "sources_present": list(sources.keys()),
        "metrics": [m.to_dict() for m in metrics],
        "ai_vs_independent_mae_improvement_percent": improvement,
    }
    eval_path = Path(args.output) / args.date / f"projection_source_comparison_{timestamp_tag(generated_at)}.json"
    save_json(eval_path, document)
    print(f"Comparison report written to: {eval_path}")
    print(json.dumps({"status": "ready", "path": str(eval_path)}))


if __name__ == "__main__":
    main()
