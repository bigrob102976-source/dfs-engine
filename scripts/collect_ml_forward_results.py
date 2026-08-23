"""CLI entry point / admin "COLLECT RESULTS" action: grade Big Money ML
(and Native/AI/FantasyPros for comparison) against REAL, postgame MLB
results for one Big Money ML-optimized DraftKings slate.

    Check MLB FINAL status (fresh, per game in the slate)
      -> collect + score only the games that are FINAL
      -> grade every player with a valid pregame projection
      -> grade every saved M32.4 lineup set for this slate
      -> compute ceiling / zero-game / disaster-pitcher monitors
      -> persist one immutable ml_forward_results/<date>/<slate_id>/... document

Never grades a pregame/in-play/suspended game as final. If the slate
isn't fully final yet, this still runs and reports PARTIAL results
honestly -- re-running it later (as more games finish) is always safe
and idempotent (results/<date>/*.json is overwritten with the same-or-
more-complete content; each ml_forward_results run is its own new
immutable snapshot, never replacing a prior one).

Usage:
    python scripts/collect_ml_forward_results.py --date YYYY-MM-DD --slate-id dkunofficial-XXXXXX
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.big_money_ml_evaluation import compute_ceiling_magnitude_monitor, compute_disaster_start_bucket, compute_zero_game_monitor  # noqa: E402
from evaluation.ml_forward_grading import (  # noqa: E402
    build_all_player_grading_records,
    build_expected_player_lists,
    check_slate_final_status,
    collect_and_score_final_games,
    compare_lineup_sources_for_slate,
    evaluate_forward_combined_performance,
    grade_lineup_sets_for_slate,
)
from evaluation.big_money_ml_evaluation import evaluate_forward_hitter_performance, evaluate_forward_performance  # noqa: E402
from evaluation.ml_forward_persistence import save_ml_forward_results_document  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and grade Big Money ML forward results for one slate.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", required=True)
    parser.add_argument("--lineup-sources", nargs="+", default=["big_money_ml", "native", "ai"])
    args = parser.parse_args()

    status = check_slate_final_status(args.date, args.slate_id)
    print(f"Slate {args.slate_id} ({args.date}): {status['games_final']}/{status['games_total']} games FINAL")
    for g in status["games"]:
        print(f"  {g['game_id']}: {g['detailed_state']} {'[FINAL]' if g['final'] else ''}")
    print()

    final_game_ids = [g["game_id"] for g in status["games"] if g["final"]]
    if not final_game_ids:
        print("No games final yet -- nothing to grade. Report status only (PARTIAL: 0 games final).")
        print(json.dumps({"status": "no_games_final", "date": args.date, "slate_id": args.slate_id, "games_total": status["games_total"], "games_final": 0}))
        return

    expected_pitchers, expected_hitters = build_expected_player_lists(args.date)
    collection = collect_and_score_final_games(args.date, final_game_ids, expected_pitchers, expected_hitters)
    print(f"Pitchers graded (this collection): {collection['pitchers_graded']}")
    print(f"Hitters graded (this collection): {collection['hitters_graded']}")
    if collection["warnings"]:
        print(f"Warnings: {len(collection['warnings'])}")
    print()

    player_grading = build_all_player_grading_records(args.date)
    ml_pitchers_graded = sum(1 for r in player_grading["pitchers"] if r["projection_source"] == "big_money_ml")
    ml_hitters_graded = sum(1 for r in player_grading["hitters"] if r["projection_source"] == "big_money_ml")

    lineup_grading = grade_lineup_sets_for_slate(args.date, args.slate_id, projection_source="big_money_ml")
    lineup_source_comparison = compare_lineup_sources_for_slate(args.date, args.slate_id, args.lineup_sources)

    pitcher_performance = evaluate_forward_performance([args.date])
    hitter_performance = evaluate_forward_hitter_performance([args.date])
    combined_performance = evaluate_forward_combined_performance([args.date])

    ceiling_monitor = compute_ceiling_magnitude_monitor([args.date])
    zero_monitor = compute_zero_game_monitor([args.date])
    disaster_monitor = compute_disaster_start_bucket([args.date])

    generated_at = datetime.now(timezone.utc).isoformat()
    document = {
        "slate_date": args.date,
        "slate_id": args.slate_id,
        "generated_at": generated_at,
        "games_total": status["games_total"],
        "games_final": status["games_final"],
        "all_final": status["all_final"],
        "games": status["games"],
        "players_graded": collection["pitchers_graded"] + collection["hitters_graded"],
        "ml_pitchers_graded": ml_pitchers_graded,
        "ml_hitters_graded": ml_hitters_graded,
        "lineups_graded": lineup_grading["lineups_fully_graded"],
        "player_grading": player_grading,
        "lineup_grading": lineup_grading,
        "lineup_source_comparison": lineup_source_comparison,
        "source_comparison": {"pitchers": pitcher_performance, "hitters": hitter_performance, "combined": combined_performance},
        "ceiling_monitor": ceiling_monitor,
        "zero_game_monitor": zero_monitor,
        "disaster_pitcher_monitor": disaster_monitor,
    }

    path = save_ml_forward_results_document(document)
    print(f"Players graded: {document['players_graded']} (ML hitters: {ml_hitters_graded}, ML pitchers: {ml_pitchers_graded})")
    print(f"Lineups graded: {document['lineups_graded']}")
    print(f"Saved: {path}")

    print(json.dumps({
        "status": "ready" if status["all_final"] else "partial",
        "date": args.date, "slate_id": args.slate_id,
        "games_total": status["games_total"], "games_final": status["games_final"],
        "players_graded": document["players_graded"], "lineups_graded": document["lineups_graded"],
        "path": str(path),
    }))


if __name__ == "__main__":
    main()
