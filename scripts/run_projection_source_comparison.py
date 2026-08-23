"""CLI entry point: compare every available pregame projection source
(Independent / External / Adjusted / AI / Native) against actual postgame
results for a slate date -- separately for pitchers, hitters, and overall
(both combined), per Milestone 23's evaluation-extension requirement.

    results/<date>/pitcher_results.json + hitter_results.json  (postgame,
        from scripts/collect_pitcher_results.py / collect_hitter_results.py)
    + predictions/<date>/pitcher_board_<ts>.json / batter_board_<ts>.json  (Independent)
    + adjusted_projection_snapshots/<date>/adjusted_<ts>.json (External + Adjusted)
    + ai_projection_snapshots/<date>/ai_projection_<ts>.json  (AI)
    + native_projection_snapshots/<date>/native_projection_<ts>.json (Native, Milestone 23)
        -> evaluation.projection_source_comparison (pitcher/hitter/overall MAE/RMSE/
           correlation/rank-correlation/top-N hit rate)
        -> evaluation.native_component_evaluation (native's own projected-K/IP/BB/
           hits/ER vs actual, and projected-HR/BB/SB vs actual, for pitchers/hitters
           respectively -- traces a bad final projection to a specific component)
        -> printed report + evaluations/<date>/projection_source_comparison_<ts>.json

Any source missing for this date is simply omitted from the comparison,
never faked. Hitter results/native results are both optional -- a date
with only pitcher data still produces a pitcher-only report (same as
before Milestone 23), and vice versa.

This script does NOT tune any model parameter based on its own output --
it only reports metrics, per the milestone's explicit "do not tune from
one slate" instruction.

Usage:
    python scripts/run_projection_source_comparison.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.native_component_evaluation import evaluate_hitter_components, evaluate_pitcher_components  # noqa: E402
from evaluation.projection_source_comparison import compare_projection_sources  # noqa: E402
from evaluation.projection_source_loader import (  # noqa: E402
    DEFAULT_NATIVE_PROJECTION_ROOT,
    build_hitter_projection_sources,
    build_pitcher_projection_sources,
    load_actual_hitter_points,
    load_actual_pitcher_points,
)
from native_projections.persistence import list_native_projection_snapshots, load_native_projection_snapshot  # noqa: E402
from research.prediction_snapshot import timestamp_tag  # noqa: E402
from research.storage import save_json  # noqa: E402

DEFAULT_EVALUATIONS_ROOT = Path(__file__).resolve().parent.parent / "evaluations"
DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"


def _fmt(value, digits=3, none_text="n/a") -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else none_text


def _print_metrics_section(title: str, metrics) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)
    if not metrics:
        print("  (no sources with data for this slate)")
        print()
        return
    for m in metrics:
        print(f"  {m.source:<12} n={m.n:<4} MAE={_fmt(m.mae, 2):<7} RMSE={_fmt(m.rmse, 2):<7} corr={_fmt(m.correlation):<7} "
              f"rank_corr={_fmt(m.rank_correlation):<7} bias={_fmt(m.bias, 2):<7} top5={_fmt(m.top5_hit_rate):<7} top10={_fmt(m.top10_hit_rate)}")
    print()


def _print_component_section(title: str, components) -> None:
    print("-" * 70)
    print(title)
    print("-" * 70)
    for c in components:
        print(f"  {c.component:<16} n={c.n:<4} MAE={_fmt(c.mae, 3):<7} mean_predicted={_fmt(c.mean_predicted, 3):<8} mean_actual={_fmt(c.mean_actual, 3)}")
    print()


def _load_latest_native_players(slate_date: str, native_root: Path):
    snapshots = list_native_projection_snapshots(slate_date, output_root=native_root)
    if not snapshots:
        return []
    return load_native_projection_snapshot(snapshots[-1]).get("players", [])


def _load_results(slate_date: str, results_root: Path, filename: str):
    path = Path(results_root) / slate_date / filename
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f).get("results", [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare every available projection source against actual postgame results.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--output", default=str(DEFAULT_EVALUATIONS_ROOT), help="Evaluations output root (default: evaluations)")
    parser.add_argument("--dk-slate-id", default=None, help="DK slate id, needed to include the BlueCollar source (slate-scoped, see bluecollar/persistence.py) -- omitted, BlueCollar is simply left out")
    args = parser.parse_args()

    actual_pitcher_by_id = load_actual_pitcher_points(args.date)
    actual_hitter_by_id = load_actual_hitter_points(args.date)
    if not actual_pitcher_by_id and not actual_hitter_by_id:
        print(f"No actual results found for {args.date}.")
        print(f"Run: python scripts/collect_pitcher_results.py --date {args.date}")
        print(f"And/or: python scripts/collect_hitter_results.py --date {args.date}")
        return

    pitcher_sources = build_pitcher_projection_sources(args.date, dk_slate_id=args.dk_slate_id)
    hitter_sources = build_hitter_projection_sources(args.date, dk_slate_id=args.dk_slate_id)
    if not pitcher_sources and not hitter_sources:
        print(f"No projection sources (independent/external/adjusted/ai/native/bluecollar) found for {args.date}.")
        return

    pitcher_metrics = compare_projection_sources(pitcher_sources, actual_pitcher_by_id) if actual_pitcher_by_id else []
    hitter_metrics = compare_projection_sources(hitter_sources, actual_hitter_by_id) if actual_hitter_by_id else []

    overall_actual = {**actual_pitcher_by_id, **actual_hitter_by_id}
    overall_sources = {
        name: {**pitcher_sources.get(name, {}), **hitter_sources.get(name, {})}
        for name in set(pitcher_sources) | set(hitter_sources)
    }
    overall_metrics = compare_projection_sources(overall_sources, overall_actual) if overall_actual else []

    independent_mae = next((m.mae for m in overall_metrics if m.source == "independent"), None)
    ai_mae = next((m.mae for m in overall_metrics if m.source == "ai"), None)
    native_mae = next((m.mae for m in overall_metrics if m.source == "native"), None)
    ai_improvement = round((independent_mae - ai_mae) / independent_mae * 100.0, 1) if independent_mae and ai_mae is not None else None
    native_improvement = round((independent_mae - native_mae) / independent_mae * 100.0, 1) if independent_mae and native_mae is not None else None

    _print_metrics_section("PITCHER PROJECTION PERFORMANCE", pitcher_metrics)
    _print_metrics_section("HITTER PROJECTION PERFORMANCE", hitter_metrics)
    _print_metrics_section("OVERALL PROJECTION PERFORMANCE (pitchers + hitters combined)", overall_metrics)
    if ai_improvement is not None:
        print(f"AI vs Independent MAE improvement: {ai_improvement:+.1f}%")
    if native_improvement is not None:
        print(f"Native vs Independent MAE improvement: {native_improvement:+.1f}%")
    print()

    native_players = _load_latest_native_players(args.date, DEFAULT_NATIVE_PROJECTION_ROOT)
    pitcher_component_results = []
    hitter_component_results = []
    if native_players:
        pitcher_results = _load_results(args.date, DEFAULT_RESULTS_ROOT, "pitcher_results.json")
        hitter_results = _load_results(args.date, DEFAULT_RESULTS_ROOT, "hitter_results.json")
        if pitcher_results:
            pitcher_component_results = evaluate_pitcher_components(native_players, pitcher_results)
            _print_component_section("NATIVE PITCHER COMPONENT EVALUATION (projected vs actual)", pitcher_component_results)
        if hitter_results:
            hitter_component_results = evaluate_hitter_components(native_players, hitter_results)
            _print_component_section("NATIVE HITTER COMPONENT EVALUATION (projected vs actual)", hitter_component_results)

    generated_at = datetime.now(timezone.utc).isoformat()
    document = {
        "slate_date": args.date,
        "generated_at": generated_at,
        "actual_pitcher_result_count": len(actual_pitcher_by_id),
        "actual_hitter_result_count": len(actual_hitter_by_id),
        "pitcher_sources_present": list(pitcher_sources.keys()),
        "hitter_sources_present": list(hitter_sources.keys()),
        "pitcher_metrics": [m.to_dict() for m in pitcher_metrics],
        "hitter_metrics": [m.to_dict() for m in hitter_metrics],
        "overall_metrics": [m.to_dict() for m in overall_metrics],
        "ai_vs_independent_mae_improvement_percent": ai_improvement,
        "native_vs_independent_mae_improvement_percent": native_improvement,
        "native_pitcher_component_evaluation": [c.to_dict() for c in pitcher_component_results],
        "native_hitter_component_evaluation": [c.to_dict() for c in hitter_component_results],
    }
    eval_path = Path(args.output) / args.date / f"projection_source_comparison_{timestamp_tag(generated_at)}.json"
    save_json(eval_path, document)
    print(f"Comparison report written to: {eval_path}")
    print(json.dumps({"status": "ready", "path": str(eval_path)}))


if __name__ == "__main__":
    main()
