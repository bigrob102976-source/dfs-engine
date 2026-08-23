"""Milestone 32.5 -- cumulative forward-history window tests: only
shows a window when enough completed slates actually exist, and flags
EARLY SAMPLE until at least 5 completed slates exist."""

import json

from evaluation.ml_forward_history import EARLY_SAMPLE_WARNING, MIN_SLATES_FOR_CONCLUSIONS, build_cumulative_forward_history
from evaluation.ml_forward_persistence import save_ml_forward_results_document


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_slate(forward_root, ml_root, results_root, date, projection=20.0, actual=22.0):
    """A minimal completed slate: one ML pitcher with a valid pregame
    projection and a real (postgame) actual result, plus its persisted
    ml_forward_results marker document."""
    _write_json(ml_root / date / "ml_projection_1.json", {
        "slate_date": date, "generated_at": f"{date}T20:00:00+00:00", "model_version": "1.0.0", "warehouse_version": "v1",
        "raw_dk_pitcher_count": 1, "starting_pitcher_count": 1, "ml_eligible_pitcher_count": 1,
        "ml_projections_generated": 1, "ml_projections_missing": 0, "feature_parity_summary": {}, "warnings": [],
        "players": [{
            "player_id": "100", "dk_player_id": "dk100", "name": "P", "team": "NYY", "opponent": "BOS", "game_id": "g1",
            "salary": 9000, "projection": projection, "model_version": "1.0.0", "data_quality_score": 0.9, "feature_coverage": 0.9,
            "missing_features": [], "projection_status": "LIVE_PREGAME", "feature_timestamp": f"{date}T20:00:00+00:00",
            "game_scheduled_start_utc": f"{date}T23:00:00Z", "warnings": [],
        }],
    })
    _write_json(results_root / date / "pitcher_results.json", {"results": [{"player_id": "100", "dfs_points": actual}]})
    save_ml_forward_results_document(
        {"slate_date": date, "slate_id": "dkunofficial-x", "generated_at": f"{date}T23:30:00+00:00", "players_graded": 1},
        output_root=forward_root,
    )


def test_early_sample_warning_shown_below_minimum(tmp_path):
    forward_root, ml_root, results_root = tmp_path / "forward", tmp_path / "ml", tmp_path / "results"
    for i, date in enumerate(["2026-08-18", "2026-08-19", "2026-08-20"]):
        _seed_slate(forward_root, ml_root, results_root, date)

    history = build_cumulative_forward_history(output_root=forward_root, results_root=results_root, ml_root=ml_root)
    assert history["total_slates_completed"] == 3
    assert history["early_sample"] is True
    assert history["early_sample_warning"] == EARLY_SAMPLE_WARNING


def test_early_sample_warning_cleared_at_minimum(tmp_path):
    forward_root, ml_root, results_root = tmp_path / "forward", tmp_path / "ml", tmp_path / "results"
    dates = [f"2026-08-{15+i}" for i in range(MIN_SLATES_FOR_CONCLUSIONS)]
    for date in dates:
        _seed_slate(forward_root, ml_root, results_root, date)

    history = build_cumulative_forward_history(output_root=forward_root, results_root=results_root, ml_root=ml_root)
    assert history["total_slates_completed"] == MIN_SLATES_FOR_CONCLUSIONS
    assert history["early_sample"] is False
    assert history["early_sample_warning"] is None


def test_window_only_shown_when_enough_slates_exist(tmp_path):
    forward_root, ml_root, results_root = tmp_path / "forward", tmp_path / "ml", tmp_path / "results"
    for date in ["2026-08-18", "2026-08-19", "2026-08-20"]:  # only 3 completed
        _seed_slate(forward_root, ml_root, results_root, date)

    history = build_cumulative_forward_history(output_root=forward_root, results_root=results_root, ml_root=ml_root)
    assert "1" in history["windows"]
    assert "3" in history["windows"]
    assert "5" not in history["windows"]  # not enough data yet -- never fabricated
    assert "10" not in history["windows"]
    assert "all" in history["windows"]


def test_window_1_reflects_only_the_most_recent_slate(tmp_path):
    forward_root, ml_root, results_root = tmp_path / "forward", tmp_path / "ml", tmp_path / "results"
    _seed_slate(forward_root, ml_root, results_root, "2026-08-18", projection=10.0, actual=10.0)  # perfect, MAE 0
    _seed_slate(forward_root, ml_root, results_root, "2026-08-19", projection=10.0, actual=20.0)  # MAE 10, most recent

    history = build_cumulative_forward_history(output_root=forward_root, results_root=results_root, ml_root=ml_root)
    window1_pitchers = history["windows"]["1"]["pitchers"]["source_metrics"]
    ml_row = next(r for r in window1_pitchers if r["source"] == "big_money_ml")
    assert ml_row["mae"] == 10.0
    assert history["windows"]["1"]["dates"] == ["2026-08-19"]


def test_no_completed_slates_returns_zero_windows(tmp_path):
    forward_root, ml_root, results_root = tmp_path / "forward", tmp_path / "ml", tmp_path / "results"
    history = build_cumulative_forward_history(output_root=forward_root, results_root=results_root, ml_root=ml_root)
    assert history["total_slates_completed"] == 0
    assert history["windows"] == {}
    assert history["early_sample"] is True
