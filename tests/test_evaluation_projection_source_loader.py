import json
from pathlib import Path

from evaluation.projection_source_loader import (
    build_pitcher_projection_sources,
    load_actual_pitcher_points,
    load_ai_pitcher_projections,
    load_external_and_adjusted_pitcher_projections,
    load_independent_pitcher_projections,
)
from external_projections.persistence import save_adjusted_snapshot
from projection_engine.persistence import save_ai_projection_snapshot

DATE = "2026-08-13"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f)


def _adjusted_snapshot_doc(records):
    return {"slate_date": DATE, "generated_at": f"{DATE}T20:00:00+00:00", "records": records}


# ----------------------------------------------------------------------------
# load_actual_pitcher_points
# ----------------------------------------------------------------------------


def test_actual_points_empty_when_missing(tmp_path):
    assert load_actual_pitcher_points(DATE, results_root=tmp_path) == {}


def test_actual_points_reads_dfs_points_by_player_id(tmp_path):
    _write(tmp_path / DATE / "pitcher_results.json", {
        "results": [
            {"player_id": "608331", "name": "Max Fried", "dfs_points": 24.05},
            {"player_id": "519242", "name": "Chris Sale", "dfs_points": 18.0},
        ],
    })
    points = load_actual_pitcher_points(DATE, results_root=tmp_path)
    assert points == {"608331": 24.05, "519242": 18.0}


def test_actual_points_skips_records_missing_dfs_points(tmp_path):
    _write(tmp_path / DATE / "pitcher_results.json", {
        "results": [{"player_id": "608331", "name": "Max Fried", "dfs_points": None}],
    })
    assert load_actual_pitcher_points(DATE, results_root=tmp_path) == {}


# ----------------------------------------------------------------------------
# load_independent_pitcher_projections
# ----------------------------------------------------------------------------


def test_independent_projections_empty_when_missing(tmp_path):
    points, path = load_independent_pitcher_projections(DATE, predictions_root=tmp_path)
    assert points == {}
    assert path is None


def test_independent_projections_reads_latest_snapshot(tmp_path):
    _write(tmp_path / DATE / "pitcher_board_20260813T180000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T18:00:00Z",
        "pitchers": [{"player_id": "608331", "name": "Max Fried", "projection": 17.9}],
    })
    _write(tmp_path / DATE / "pitcher_board_20260813T190000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T19:00:00Z",
        "pitchers": [{"player_id": "608331", "name": "Max Fried", "projection": 18.5}],
    })
    points, path = load_independent_pitcher_projections(DATE, predictions_root=tmp_path)
    assert points == {"608331": 18.5}  # latest snapshot wins
    assert path is not None and "190000" in path


def test_independent_projections_skips_missing_projection(tmp_path):
    _write(tmp_path / DATE / "pitcher_board_20260813T180000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T18:00:00Z",
        "pitchers": [{"player_id": "608331", "name": "Max Fried", "projection": None}],
    })
    points, _ = load_independent_pitcher_projections(DATE, predictions_root=tmp_path)
    assert points == {}


# ----------------------------------------------------------------------------
# load_external_and_adjusted_pitcher_projections
# ----------------------------------------------------------------------------


def test_external_and_adjusted_empty_when_no_snapshot(tmp_path):
    external, adjusted, path = load_external_and_adjusted_pitcher_projections(DATE, adjusted_root=tmp_path)
    assert external == {}
    assert adjusted == {}
    assert path is None


def test_external_and_adjusted_filters_to_pitchers_only(tmp_path):
    doc = _adjusted_snapshot_doc([
        {"independent_player_id": "608331", "player_type": "pitcher", "external_projection": 19.9, "adjusted_projection": 20.2},
        {"independent_player_id": "h1", "player_type": "hitter", "external_projection": 10.0, "adjusted_projection": 10.5},
    ])
    save_adjusted_snapshot(doc, output_root=tmp_path)

    external, adjusted, _ = load_external_and_adjusted_pitcher_projections(DATE, adjusted_root=tmp_path)
    assert external == {"608331": 19.9}
    assert adjusted == {"608331": 20.2}


def test_external_and_adjusted_omits_none_values(tmp_path):
    doc = _adjusted_snapshot_doc([
        {"independent_player_id": "608331", "player_type": "pitcher", "external_projection": 19.9, "adjusted_projection": None},
    ])
    save_adjusted_snapshot(doc, output_root=tmp_path)

    external, adjusted, _ = load_external_and_adjusted_pitcher_projections(DATE, adjusted_root=tmp_path)
    assert external == {"608331": 19.9}
    assert adjusted == {}


# ----------------------------------------------------------------------------
# load_ai_pitcher_projections
# ----------------------------------------------------------------------------


def test_ai_projections_empty_when_no_snapshot(tmp_path):
    points, path = load_ai_pitcher_projections(DATE, ai_root=tmp_path)
    assert points == {}
    assert path is None


def test_ai_projections_filters_to_pitchers_only(tmp_path):
    doc = {
        "slate_date": DATE, "generated_at": f"{DATE}T21:00:00+00:00",
        "players": [
            {"player_id": "608331", "player_type": "pitcher", "ai_projection": 20.5},
            {"player_id": "h1", "player_type": "hitter", "ai_projection": 11.0},
        ],
    }
    save_ai_projection_snapshot(doc, output_root=tmp_path)

    points, _ = load_ai_pitcher_projections(DATE, ai_root=tmp_path)
    assert points == {"608331": 20.5}


# ----------------------------------------------------------------------------
# build_pitcher_projection_sources
# ----------------------------------------------------------------------------


def test_build_sources_omits_missing_sources_entirely(tmp_path):
    sources = build_pitcher_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted", ai_root=tmp_path / "ai",
    )
    assert sources == {}


def test_build_sources_includes_only_whats_present(tmp_path):
    predictions_root = tmp_path / "predictions"
    ai_root = tmp_path / "ai"
    _write(predictions_root / DATE / "pitcher_board_20260813T180000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T18:00:00Z",
        "pitchers": [{"player_id": "608331", "name": "Max Fried", "projection": 17.9}],
    })
    save_ai_projection_snapshot(
        {"slate_date": DATE, "generated_at": f"{DATE}T21:00:00+00:00",
         "players": [{"player_id": "608331", "player_type": "pitcher", "ai_projection": 20.5}]},
        output_root=ai_root,
    )

    sources = build_pitcher_projection_sources(
        DATE, predictions_root=predictions_root, adjusted_root=tmp_path / "adjusted", ai_root=ai_root,
    )
    assert sources == {"independent": {"608331": 17.9}, "ai": {"608331": 20.5}}
    assert "external" not in sources
    assert "adjusted" not in sources
