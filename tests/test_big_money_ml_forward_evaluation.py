"""Milestone 32.2B -- forward-evaluation tests: pregame-only ML
inclusion, shared-sample-N reporting, disaster-start bucket. All
synthetic fixtures under tmp_path -- no network calls."""

import json

from evaluation.big_money_ml_evaluation import (
    build_all_pitcher_projection_sources,
    compute_disaster_start_bucket,
    evaluate_forward_performance,
    load_pregame_ml_pitcher_projections,
)


def _write_ml_snapshot(root, date, players):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"slate_date": date, "generated_at": f"{date}T12:00:00+00:00", "players": players}
    (folder / "ml_projection_20260822T120000.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_results(root, date, results):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pitcher_results.json").write_text(json.dumps({"results": results}), encoding="utf-8")


def _ml_player(player_id, projection, status="LIVE_PREGAME"):
    return {"player_id": player_id, "projection": projection, "projection_status": status}


def test_load_pregame_ml_projections_excludes_missing_and_invalid(tmp_path):
    _write_ml_snapshot(tmp_path, "2026-08-22", [
        _ml_player("1", 12.0, "LIVE_PREGAME"),
        _ml_player("2", 8.0, "PREGAME_FROZEN"),
        _ml_player("3", None, "MISSING"),
        _ml_player("4", None, "INVALID_FEATURE_PARITY"),
    ])
    projections = load_pregame_ml_pitcher_projections("2026-08-22", ml_root=tmp_path)
    assert projections == {"1": 12.0, "2": 8.0}


def test_load_pregame_ml_projections_returns_empty_when_no_snapshot(tmp_path):
    assert load_pregame_ml_pitcher_projections("2026-08-22", ml_root=tmp_path) == {}


def test_build_all_sources_includes_big_money_ml_when_present(tmp_path):
    ml_root = tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0)])
    sources = build_all_pitcher_projection_sources("2026-08-22", ml_root=ml_root, fantasypros_root=tmp_path / "fp")
    assert sources.get("big_money_ml") == {"1": 10.0}


def test_evaluate_forward_performance_skips_dates_with_no_actual_results(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0)])
    # No results written for this date at all.
    performance = evaluate_forward_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert performance["slates_with_actual_results"] == 0
    assert performance["source_metrics"] == []


def test_evaluate_forward_performance_computes_shared_sample_and_metrics(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0), _ml_player("2", 15.0), _ml_player("3", 5.0)])
    _write_results(results_root, "2026-08-22", [
        {"player_id": "1", "dfs_points": 12.0}, {"player_id": "2", "dfs_points": 14.0}, {"player_id": "3", "dfs_points": 4.0},
    ])
    performance = evaluate_forward_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert performance["slates_with_actual_results"] == 1
    assert performance["slates_with_ml_pregame_data"] == 1

    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["shared_sample_n"] == 3
    assert ml_row["mae"] is not None
    assert ml_row["dates_included"] == 1


def test_evaluate_forward_performance_pools_weighted_metrics_across_multiple_dates(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-20", [_ml_player("1", 10.0), _ml_player("2", 10.0)])
    _write_results(results_root, "2026-08-20", [{"player_id": "1", "dfs_points": 10.0}, {"player_id": "2", "dfs_points": 10.0}])  # perfect, MAE=0

    _write_ml_snapshot(ml_root, "2026-08-21", [_ml_player("3", 10.0)])
    _write_results(results_root, "2026-08-21", [{"player_id": "3", "dfs_points": 20.0}])  # MAE=10

    performance = evaluate_forward_performance(["2026-08-20", "2026-08-21"], results_root=results_root, ml_root=ml_root)
    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["shared_sample_n"] == 3
    # weighted mean: (0*2 + 10*1) / 3 = 3.33
    assert abs(ml_row["mae"] - 3.333) < 0.01


def test_compute_disaster_start_bucket_only_includes_low_actual_points(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 15.0), _ml_player("2", 3.0)])
    _write_results(results_root, "2026-08-22", [
        {"player_id": "1", "dfs_points": -5.0},  # disaster start, big miss
        {"player_id": "2", "dfs_points": 25.0},  # not a disaster start -- excluded from this bucket
    ])
    bucket = compute_disaster_start_bucket(["2026-08-22"], threshold=2.0, results_root=results_root, ml_root=ml_root)
    assert bucket["n"] == 1
    assert bucket["bias"] == 20.0  # predicted 15.0 - actual -5.0
    assert bucket["dates_with_disaster_starts"] == 1


def test_compute_disaster_start_bucket_returns_zero_when_no_disasters(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 15.0)])
    _write_results(results_root, "2026-08-22", [{"player_id": "1", "dfs_points": 18.0}])
    bucket = compute_disaster_start_bucket(["2026-08-22"], threshold=2.0, results_root=results_root, ml_root=ml_root)
    assert bucket["n"] == 0
    assert bucket["bias"] is None
