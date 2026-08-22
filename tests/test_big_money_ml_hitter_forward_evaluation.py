"""Milestone 32.3B -- HITTER forward-evaluation tests: pregame-only ML
inclusion, shared-sample-N reporting, ceiling magnitude monitor,
zero-game monitor. All synthetic fixtures under tmp_path -- no network
calls. Mirrors tests/test_big_money_ml_forward_evaluation.py exactly."""

import json

from evaluation.big_money_ml_evaluation import (
    build_all_hitter_projection_sources,
    compute_ceiling_magnitude_monitor,
    compute_zero_game_monitor,
    evaluate_forward_hitter_performance,
    load_pregame_ml_hitter_projections,
)


def _write_ml_snapshot(root, date, players):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"slate_date": date, "generated_at": f"{date}T12:00:00+00:00", "players": players}
    (folder / "ml_hitter_projection_20260822T120000.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_results(root, date, results):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hitter_results.json").write_text(json.dumps({"results": results}), encoding="utf-8")


def _ml_player(player_id, projection, status="LIVE_PREGAME"):
    return {"player_id": player_id, "projection": projection, "projection_status": status}


def test_load_pregame_ml_projections_excludes_missing_and_invalid(tmp_path):
    _write_ml_snapshot(tmp_path, "2026-08-22", [
        _ml_player("1", 12.0, "LIVE_PREGAME"),
        _ml_player("2", 8.0, "PREGAME_FROZEN"),
        _ml_player("3", None, "MISSING"),
        _ml_player("4", None, "INVALID_FEATURE_PARITY"),
    ])
    projections = load_pregame_ml_hitter_projections("2026-08-22", ml_root=tmp_path)
    assert projections == {"1": 12.0, "2": 8.0}


def test_load_pregame_ml_projections_returns_empty_when_no_snapshot(tmp_path):
    assert load_pregame_ml_hitter_projections("2026-08-22", ml_root=tmp_path) == {}


def test_build_all_sources_includes_big_money_ml_when_present(tmp_path):
    ml_root = tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0)])
    sources = build_all_hitter_projection_sources("2026-08-22", ml_root=ml_root, fantasypros_root=tmp_path / "fp")
    assert sources.get("big_money_ml") == {"1": 10.0}


def test_evaluate_forward_hitter_performance_skips_dates_with_no_actual_results(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0)])
    performance = evaluate_forward_hitter_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert performance["slates_with_actual_results"] == 0
    assert performance["source_metrics"] == []


def test_evaluate_forward_hitter_performance_computes_shared_sample_and_metrics(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 10.0), _ml_player("2", 15.0), _ml_player("3", 5.0)])
    _write_results(results_root, "2026-08-22", [
        {"player_id": "1", "dfs_points": 12.0}, {"player_id": "2", "dfs_points": 14.0}, {"player_id": "3", "dfs_points": 4.0},
    ])
    performance = evaluate_forward_hitter_performance(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert performance["slates_with_actual_results"] == 1
    assert performance["slates_with_ml_pregame_data"] == 1

    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["shared_sample_n"] == 3
    assert ml_row["mae"] is not None
    assert ml_row["dates_included"] == 1


def test_evaluate_forward_hitter_performance_pools_weighted_metrics_across_multiple_dates(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-20", [_ml_player("1", 10.0), _ml_player("2", 10.0)])
    _write_results(results_root, "2026-08-20", [{"player_id": "1", "dfs_points": 10.0}, {"player_id": "2", "dfs_points": 10.0}])  # perfect, MAE=0

    _write_ml_snapshot(ml_root, "2026-08-21", [_ml_player("3", 10.0)])
    _write_results(results_root, "2026-08-21", [{"player_id": "3", "dfs_points": 20.0}])  # MAE=10

    performance = evaluate_forward_hitter_performance(["2026-08-20", "2026-08-21"], results_root=results_root, ml_root=ml_root)
    ml_row = next(r for r in performance["source_metrics"] if r["source"] == "big_money_ml")
    assert ml_row["shared_sample_n"] == 3
    # weighted mean: (0*2 + 10*1) / 3 = 3.33
    assert abs(ml_row["mae"] - 3.333) < 0.01


def test_compute_ceiling_magnitude_monitor_reports_bias_per_threshold(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 15.0), _ml_player("2", 20.0), _ml_player("3", 5.0)])
    _write_results(results_root, "2026-08-22", [
        {"player_id": "1", "dfs_points": 22.0},  # actual >= 20 -- under-projected by 7
        {"player_id": "2", "dfs_points": 30.0},  # actual >= 20, 25, and 30 -- under-projected by 10
        {"player_id": "3", "dfs_points": 4.0},  # not a ceiling event
    ])
    monitor = compute_ceiling_magnitude_monitor(["2026-08-22"], thresholds=(20.0, 25.0, 30.0), results_root=results_root, ml_root=ml_root)
    assert monitor["dates_with_ceiling_events"] == 1
    assert monitor["thresholds"]["20.0"]["n"] == 2
    assert monitor["thresholds"]["25.0"]["n"] == 1
    assert monitor["thresholds"]["30.0"]["n"] == 1
    assert monitor["thresholds"]["30.0"]["avg_predicted"] == 20.0
    assert monitor["thresholds"]["30.0"]["avg_actual"] == 30.0
    assert monitor["thresholds"]["30.0"]["bias"] == -10.0  # under-projection, negative bias


def test_compute_ceiling_magnitude_monitor_returns_none_when_no_ceiling_events(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 5.0)])
    _write_results(results_root, "2026-08-22", [{"player_id": "1", "dfs_points": 4.0}])
    monitor = compute_ceiling_magnitude_monitor(["2026-08-22"], thresholds=(20.0,), results_root=results_root, ml_root=ml_root)
    assert monitor["thresholds"]["20.0"]["n"] == 0
    assert monitor["thresholds"]["20.0"]["bias"] is None


def test_compute_zero_game_monitor_reports_over_projection_bias(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 6.0), _ml_player("2", 2.0)])
    _write_results(results_root, "2026-08-22", [
        {"player_id": "1", "dfs_points": 0.0},  # zero-point game -- over-projected by 6
        {"player_id": "2", "dfs_points": 8.0},  # not a zero game -- excluded from this bucket
    ])
    monitor = compute_zero_game_monitor(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert monitor["n"] == 1
    assert monitor["avg_predicted"] == 6.0
    assert monitor["bias"] == 6.0  # predicted 6.0 - actual 0.0, positive = over-projection
    assert monitor["dates_with_zero_games"] == 1


def test_compute_zero_game_monitor_returns_none_when_no_zero_games(tmp_path):
    results_root, ml_root = tmp_path / "results", tmp_path / "ml"
    _write_ml_snapshot(ml_root, "2026-08-22", [_ml_player("1", 6.0)])
    _write_results(results_root, "2026-08-22", [{"player_id": "1", "dfs_points": 8.0}])
    monitor = compute_zero_game_monitor(["2026-08-22"], results_root=results_root, ml_root=ml_root)
    assert monitor["n"] == 0
    assert monitor["bias"] is None
