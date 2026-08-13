"""CLI entry point: evaluate Ownership Model V1 against actual (post-lock)
DraftKings contest ownership.

    ownership_predictions/<date>/ownership_<ts>.json  (pregame, immutable)
        + a user-provided DK contest-results/standings CSV (post-lock)
        -> evaluation.actual_ownership_parser / _resolver (join by DK ID /
           crosswalk / normalized name -- never fuzzy)
        -> actual_ownership/<date>/contest_<id>_<ts>.json  (immutable import)
        -> evaluation.ownership_evaluator
        -> printed report + ownership_evaluations/<date>/contest_<id>_ownership_eval_<ts>.json (+ .csv)

This script reads actual_ownership/ and ownership_evaluations/ -- it must
NEVER be imported by, or feed data back into, the pregame ownership model
or optimizer pipeline. It does not change any ownership model weight or
threshold; it only measures. See tests/test_architecture_separation.py.

Usage:
    python scripts/evaluate_dk_ownership.py --date YYYY-MM-DD \
        --ownership ownership_predictions/YYYY-MM-DD/ownership_<timestamp>.json \
        --results data/dk/results/contest.csv
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.actual_ownership_parser import DKResultsFormatError, parse_dk_results_csv
from evaluation.actual_ownership_persistence import build_actual_ownership_document, save_actual_ownership_document
from evaluation.actual_ownership_resolver import resolve_actual_ownership
from evaluation.ownership_evaluation_persistence import build_evaluation_document, save_evaluation_csv, save_evaluation_json
from evaluation.ownership_evaluator import evaluate_ownership
from research.prediction_snapshot import timestamp_tag

TOP_N_TABLE = 15


def _load_json(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_crosswalk(path):
    if not path:
        return {}
    return _load_json(path)


def _fmt(value, digits=2, none_text="n/a") -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else none_text


def _print_player_row(r) -> str:
    return (
        f"  {r['name']:<24} sal={r.get('salary') or 0:<6} proj={_fmt(r['projected_ownership'],1):<7} "
        f"actual={_fmt(r['actual_ownership'],1):<7} err={_fmt(r['error'],1):<7} "
        f"proj_rk={r['projected_rank']!s:<4} act_rk={r['actual_rank']!s:<4}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Ownership Model V1 against actual DraftKings contest ownership.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--ownership", required=True, help="Path to an ownership_<timestamp>.json snapshot")
    parser.add_argument("--results", required=True, help="Path to a DraftKings contest-results/standings CSV")
    parser.add_argument("--crosswalk", default=None, help="Optional JSON file: {dk_player_id: mlb_player_id}")
    parser.add_argument("--actual-ownership-root", default="actual_ownership")
    parser.add_argument("--output-root", default="ownership_evaluations")
    parser.add_argument("--top-n", type=int, default=TOP_N_TABLE, help="Player table size, sorted by |error| descending")
    args = parser.parse_args()

    print("=" * 70)
    print("OWNERSHIP MODEL EVALUATION")
    print("=" * 70)

    snapshot = _load_json(args.ownership)

    try:
        raw_rows, contest_meta, format_used, warnings = parse_dk_results_csv(args.results)
    except (DKResultsFormatError, FileNotFoundError) as e:
        print(f"\nERROR: {e}")
        return

    print(f"\nSlate: {args.date}")
    print(f"Ownership Model: {snapshot.get('model_version', 'unknown')}")
    print(f"Contest: {contest_meta.contest_id or 'unknown'} ({format_used})")
    print(f"Entries: {contest_meta.entries}")
    if warnings:
        print(f"Parse warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    crosswalk = _load_crosswalk(args.crosswalk)
    actual_records = resolve_actual_ownership(raw_rows, snapshot["players"], contest_meta, Path(args.results).name, crosswalk)
    actual_doc = build_actual_ownership_document(args.date, contest_meta, format_used, warnings, actual_records)

    ts = timestamp_tag(datetime.now(timezone.utc).isoformat())
    actual_path = save_actual_ownership_document(actual_doc, args.date, ts, output_root=args.actual_ownership_root)
    print(f"\nActual ownership imported (immutable): {actual_path}")
    print(f"Matched Players: {actual_doc['matched_count']} / {actual_doc['record_count']} "
          f"(unmatched {actual_doc['unmatched_count']}, ambiguous {actual_doc['ambiguous_count']})")

    report = evaluate_ownership(snapshot, actual_doc, ownership_snapshot_path=args.ownership)
    d = report.to_dict()

    print("\nOVERALL")
    om = d["overall_metrics"]
    print(f"MAE: {_fmt(om['mae'])}")
    print(f"RMSE: {_fmt(om['rmse'])}")
    print(f"Correlation: {_fmt(om['correlation'], 3)}")
    print(f"Rank Correlation: {_fmt(om['rank_correlation'], 3)}")
    print(f"Bias: {_fmt(om['bias'])}")

    print("\nPITCHERS")
    pm = d["pitcher_metrics"]
    print(f"MAE: {_fmt(pm['mae'])}")
    print(f"Correlation: {_fmt(pm['correlation'], 3)}")

    print("\nHITTERS")
    hm = d["hitter_metrics"]
    print(f"MAE: {_fmt(hm['mae'])}")
    print(f"Correlation: {_fmt(hm['correlation'], 3)}")

    print("\nTOP ACTUAL OWNERSHIP")
    for r in d["top_actual_ownership"]:
        print(_print_player_row(r))

    print("\nBIGGEST UNDER-PROJECTIONS (actual >> projected)")
    for r in d["biggest_under_projections"]:
        print(_print_player_row(r))

    print("\nBIGGEST OVER-PROJECTIONS (projected >> actual)")
    for r in d["biggest_over_projections"]:
        print(_print_player_row(r))

    print("\nPROJECTED VS ACTUAL CHALK")
    ce = d["chalk_evaluation"]
    print(f"Mode: {ce['mode']}  Predicted chalk: {ce['predicted_chalk_count']}  Actual chalk: {ce['actual_chalk_count']}")
    print(f"Precision: {_fmt(ce['precision'], 3)}  Recall: {_fmt(ce['recall'], 3)}")
    print(f"Top-5 hit rate: {_fmt(d['top5_hit_rate'], 3)}  Top-10 hit rate: {_fmt(d['top10_hit_rate'], 3)}")

    print("\nTIER PERFORMANCE")
    for t in d["tier_summary"]:
        print(f"  {t['tier']:<10} n={t['count']:<4} avg_proj={_fmt(t['avg_projected_ownership']):<7} "
              f"avg_actual={_fmt(t['avg_actual_ownership']):<7} mae={_fmt(t['mae'])}")

    print("\nTEAM POPULARITY (aggregate player ownership by team -- NOT stack ownership)")
    for t in d["team_popularity_evaluation"][:10]:
        print(f"  {t['team']:<6} proj_agg={_fmt(t['projected_aggregate_player_ownership']):<8} "
              f"actual_agg={_fmt(t['actual_aggregate_player_ownership']):<8} "
              f"proj_rk={t['projected_rank']!s:<4} act_rk={t['actual_rank']!s:<4}")

    print("\nTAG PERFORMANCE")
    for t in d["tag_performance"]:
        print(f"  {t['tag']:<20} n={t['count']:<4} avg_proj={_fmt(t['avg_projected_ownership']):<7} "
              f"avg_actual={_fmt(t['avg_actual_ownership']):<7} avg_err={_fmt(t['avg_error'])}")

    matched_records = [r for r in d["records"] if r["matched"] and r["error"] is not None]
    print(f"\nPLAYER TABLE (top {args.top_n} by |error|)")
    for r in sorted(matched_records, key=lambda r: -abs(r["error"]))[: args.top_n]:
        print(_print_player_row(r))

    generated_at = datetime.now(timezone.utc).isoformat()
    document = build_evaluation_document(d, generated_at)
    contest_id = contest_meta.contest_id or "unknown"
    ts2 = timestamp_tag(generated_at)
    json_path = save_evaluation_json(document, args.date, contest_id, ts2, output_root=args.output_root)
    csv_path = save_evaluation_csv(document, args.date, contest_id, ts2, output_root=args.output_root)

    print("\nFiles written:")
    print(f"  - {actual_path}")
    print(f"  - {json_path}")
    print(f"  - {csv_path}")


if __name__ == "__main__":
    main()
