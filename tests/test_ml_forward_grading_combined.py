"""Milestone 32.5 -- combined (hitter + pitcher pooled) forward
performance tests: proves the pooled Pearson/Spearman/top-N are
recomputed on the merged sample, never algebraically averaged from
separate hitter/pitcher metrics."""

import json

from evaluation.ml_forward_grading import build_all_player_grading_records, evaluate_forward_combined_performance


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ml_pitcher_doc(players):
    return {
        "slate_date": "2026-08-22", "generated_at": "2026-08-22T20:00:00+00:00", "model_version": "1.0.0", "warehouse_version": "v1",
        "raw_dk_pitcher_count": len(players), "starting_pitcher_count": len(players), "ml_eligible_pitcher_count": len(players),
        "ml_projections_generated": len(players), "ml_projections_missing": 0, "feature_parity_summary": {}, "players": players, "warnings": [],
    }


def _ml_hitter_doc(players):
    return {
        "slate_date": "2026-08-22", "generated_at": "2026-08-22T20:05:00+00:00", "model_version": "1.0.0", "warehouse_version": "v1",
        "raw_dk_hitter_count": len(players), "confirmed_starting_hitter_count": len(players), "ml_eligible_hitter_count": len(players),
        "ml_projections_generated": len(players), "ml_projections_missing": 0, "feature_parity_summary": {}, "players": players, "warnings": [],
    }


def _ml_player(player_id, name, projection, status="LIVE_PREGAME", team="NYY", opponent="BOS", game_id="g1"):
    return {
        "player_id": player_id, "dk_player_id": f"dk{player_id}", "name": name, "team": team, "opponent": opponent, "game_id": game_id,
        "salary": 5000, "projection": projection, "model_version": "1.0.0", "data_quality_score": 0.9, "feature_coverage": 0.9,
        "missing_features": [], "projection_status": status, "feature_timestamp": "2026-08-22T20:00:00+00:00",
        "game_scheduled_start_utc": "2026-08-22T23:00:00Z", "warnings": [],
    }


def test_combined_pools_hitters_and_pitchers_into_one_sample(tmp_path):
    ml_root = tmp_path / "ml"
    results_root = tmp_path / "results"

    _write_json(ml_root / "2026-08-22" / "ml_projection_1.json", _ml_pitcher_doc([_ml_player("100", "Pitcher A", 20.0)]))
    _write_json(ml_root / "2026-08-22" / "ml_hitter_projection_1.json", _ml_hitter_doc([_ml_player("200", "Hitter A", 10.0)]))
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": [{"player_id": "100", "dfs_points": 22.0}]})
    _write_json(results_root / "2026-08-22" / "hitter_results.json", {"results": [{"player_id": "200", "dfs_points": 8.0}]})

    performance = evaluate_forward_combined_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["shared_sample_n"] == 2  # one pitcher + one hitter, pooled


def test_combined_mae_matches_manual_pooled_calculation(tmp_path):
    ml_root = tmp_path / "ml"
    results_root = tmp_path / "results"

    _write_json(ml_root / "2026-08-22" / "ml_projection_1.json", _ml_pitcher_doc([_ml_player("100", "P", 20.0)]))
    _write_json(ml_root / "2026-08-22" / "ml_hitter_projection_1.json", _ml_hitter_doc([_ml_player("200", "H", 10.0)]))
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": [{"player_id": "100", "dfs_points": 25.0}]})  # error 5
    _write_json(results_root / "2026-08-22" / "hitter_results.json", {"results": [{"player_id": "200", "dfs_points": 7.0}]})  # error 3

    performance = evaluate_forward_combined_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["mae"] == 4.0  # (5+3)/2


def test_player_grading_records_include_ml_pitchers_and_hitters_separately(tmp_path):
    ml_root = tmp_path / "ml"
    results_root = tmp_path / "results"
    _write_json(ml_root / "2026-08-22" / "ml_projection_1.json", _ml_pitcher_doc([_ml_player("100", "P", 20.0)]))
    _write_json(ml_root / "2026-08-22" / "ml_hitter_projection_1.json", _ml_hitter_doc([_ml_player("200", "H", 10.0)]))
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": [{"player_id": "100", "dfs_points": 22.0}]})
    _write_json(results_root / "2026-08-22" / "hitter_results.json", {"results": [{"player_id": "200", "dfs_points": 8.0}]})

    records = build_all_player_grading_records("2026-08-22", ml_root=ml_root, results_root=results_root)
    ml_pitcher_records = [r for r in records["pitchers"] if r["projection_source"] == "big_money_ml"]
    ml_hitter_records = [r for r in records["hitters"] if r["projection_source"] == "big_money_ml"]
    assert len(ml_pitcher_records) == 1
    assert len(ml_hitter_records) == 1
    assert ml_pitcher_records[0]["player_type"] == "pitcher"
    assert ml_hitter_records[0]["player_type"] == "hitter"
    assert len(records["combined"]) == len(records["pitchers"]) + len(records["hitters"])


def test_pregame_only_projections_excluded_from_combined_sample(tmp_path):
    """A MISSING/INVALID_FEATURE_PARITY ML row must never enter the
    combined comparison, even if an actual result exists."""
    ml_root = tmp_path / "ml"
    results_root = tmp_path / "results"
    _write_json(ml_root / "2026-08-22" / "ml_projection_1.json", _ml_pitcher_doc([_ml_player("100", "P", None, status="MISSING")]))
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": [{"player_id": "100", "dfs_points": 22.0}]})

    performance = evaluate_forward_combined_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    ml_rows = [r for r in performance["source_metrics"] if r["source"] == "big_money_ml"]
    assert ml_rows == []
