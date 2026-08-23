"""Milestone 32.5 -- ml_forward_results snapshot persistence tests:
immutability, (date, slate_id) isolation, chronological listing."""

import pytest

from evaluation.ml_forward_persistence import (
    list_all_ml_forward_results_slates,
    list_ml_forward_results_snapshots,
    load_latest_ml_forward_results,
    save_ml_forward_results_document,
)


def _doc(slate_date, slate_id, generated_at, players_graded=10):
    return {"slate_date": slate_date, "slate_id": slate_id, "generated_at": generated_at, "players_graded": players_graded}


def test_save_and_load_round_trips(tmp_path):
    doc = _doc("2026-08-22", "dkunofficial-152547", "2026-08-22T23:00:00+00:00")
    path = save_ml_forward_results_document(doc, output_root=tmp_path)
    assert path.exists()
    loaded = load_latest_ml_forward_results("2026-08-22", "dkunofficial-152547", output_root=tmp_path)
    assert loaded["players_graded"] == 10


def test_save_never_overwrites_an_existing_snapshot(tmp_path):
    doc = _doc("2026-08-22", "dkunofficial-152547", "2026-08-22T23:00:00+00:00")
    save_ml_forward_results_document(doc, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_ml_forward_results_document(doc, output_root=tmp_path)


def test_snapshots_isolated_by_slate_id_never_overwrite_a_different_slate_same_date(tmp_path):
    """Do not overwrite prior slates -- two different slate_ids on the
    SAME date must both persist independently."""
    save_ml_forward_results_document(_doc("2026-08-22", "dkunofficial-AAA", "2026-08-22T20:00:00+00:00", players_graded=5), output_root=tmp_path)
    save_ml_forward_results_document(_doc("2026-08-22", "dkunofficial-BBB", "2026-08-22T21:00:00+00:00", players_graded=99), output_root=tmp_path)

    a = load_latest_ml_forward_results("2026-08-22", "dkunofficial-AAA", output_root=tmp_path)
    b = load_latest_ml_forward_results("2026-08-22", "dkunofficial-BBB", output_root=tmp_path)
    assert a["players_graded"] == 5
    assert b["players_graded"] == 99


def test_snapshots_isolated_by_date(tmp_path):
    save_ml_forward_results_document(_doc("2026-08-21", "dkunofficial-152400", "2026-08-21T20:00:00+00:00", players_graded=1), output_root=tmp_path)
    save_ml_forward_results_document(_doc("2026-08-22", "dkunofficial-152547", "2026-08-22T20:00:00+00:00", players_graded=2), output_root=tmp_path)
    day1 = load_latest_ml_forward_results("2026-08-21", "dkunofficial-152400", output_root=tmp_path)
    day2 = load_latest_ml_forward_results("2026-08-22", "dkunofficial-152547", output_root=tmp_path)
    assert day1["players_graded"] == 1
    assert day2["players_graded"] == 2


def test_list_snapshots_returns_empty_for_a_slate_with_no_collection_runs(tmp_path):
    assert list_ml_forward_results_snapshots("2099-01-01", "dkunofficial-none", output_root=tmp_path) == []
    assert load_latest_ml_forward_results("2099-01-01", "dkunofficial-none", output_root=tmp_path) is None


def test_list_snapshots_is_chronologically_sorted_latest_wins(tmp_path):
    save_ml_forward_results_document(_doc("2026-08-22", "dkunofficial-152547", "2026-08-22T20:00:00+00:00", players_graded=1), output_root=tmp_path)
    save_ml_forward_results_document(_doc("2026-08-22", "dkunofficial-152547", "2026-08-22T22:00:00+00:00", players_graded=2), output_root=tmp_path)
    snapshots = list_ml_forward_results_snapshots("2026-08-22", "dkunofficial-152547", output_root=tmp_path)
    assert len(snapshots) == 2
    latest = load_latest_ml_forward_results("2026-08-22", "dkunofficial-152547", output_root=tmp_path)
    assert latest["players_graded"] == 2  # the later-timestamped run wins "latest" (more games final)


def test_list_all_slates_returns_one_latest_document_per_date_slate_pair(tmp_path):
    save_ml_forward_results_document(_doc("2026-08-20", "dkunofficial-A", "2026-08-20T20:00:00+00:00", players_graded=1), output_root=tmp_path)
    save_ml_forward_results_document(_doc("2026-08-21", "dkunofficial-B", "2026-08-21T20:00:00+00:00", players_graded=2), output_root=tmp_path)
    save_ml_forward_results_document(_doc("2026-08-21", "dkunofficial-B", "2026-08-21T22:00:00+00:00", players_graded=3), output_root=tmp_path)

    slates = list_all_ml_forward_results_slates(output_root=tmp_path)
    assert len(slates) == 2  # one per (date, slate_id) pair, latest run each
    dates = [s["slate_date"] for s in slates]
    assert dates == ["2026-08-20", "2026-08-21"]  # chronological
    by_date = {s["slate_date"]: s for s in slates}
    assert by_date["2026-08-21"]["players_graded"] == 3  # latest run for that slate


def test_list_all_slates_empty_root_returns_empty_list(tmp_path):
    assert list_all_ml_forward_results_slates(output_root=tmp_path / "does-not-exist") == []
