import json
from pathlib import Path

from evaluation.projection_source_loader import (
    build_hitter_projection_sources,
    build_pitcher_projection_sources,
    load_actual_hitter_points,
    load_ai_hitter_projections,
    load_external_and_adjusted_hitter_projections,
    load_independent_hitter_projections,
    load_native_hitter_projections,
    load_native_pitcher_projections,
)
from external_projections.persistence import save_adjusted_snapshot
from native_projections.persistence import save_native_projection_document
from native_projections.models import NativePlayerProjection, NativeProjectionDocument
from projection_engine.persistence import save_ai_projection_snapshot

DATE = "2026-08-13"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f)


def _adjusted_snapshot_doc(records):
    return {"slate_date": DATE, "generated_at": f"{DATE}T20:00:00+00:00", "records": records}


def _native_document(players):
    return NativeProjectionDocument(
        slate_date=DATE, generated_at=f"{DATE}T20:00:00+00:00", model_version="1.0.0",
        pitcher_snapshot_path=None, batter_snapshot_path=None, environment_snapshot_path=None,
        player_count=len(players), players=players,
    )


def _native_player(player_id, player_type, native_projection):
    return NativePlayerProjection(
        player_id=player_id, name=f"Player {player_id}", team="AAA", player_type=player_type,
        native_projection=native_projection,
    )


# ----------------------------------------------------------------------------
# Native loaders
# ----------------------------------------------------------------------------


def test_native_pitcher_projections_empty_when_missing(tmp_path):
    points, path = load_native_pitcher_projections(DATE, native_root=tmp_path)
    assert points == {}
    assert path is None


def test_native_projections_filter_by_player_type(tmp_path):
    doc = _native_document([
        _native_player("1", "pitcher", 20.5),
        _native_player("2", "hitter", 8.5),
    ])
    save_native_projection_document(doc, output_root=tmp_path)

    pitcher_points, _ = load_native_pitcher_projections(DATE, native_root=tmp_path)
    hitter_points, _ = load_native_hitter_projections(DATE, native_root=tmp_path)
    assert pitcher_points == {"1": 20.5}
    assert hitter_points == {"2": 8.5}


# ----------------------------------------------------------------------------
# Hitter equivalents of the pitcher loaders
# ----------------------------------------------------------------------------


def test_actual_hitter_points_reads_dfs_points_by_player_id(tmp_path):
    _write(tmp_path / DATE / "hitter_results.json", {
        "results": [{"player_id": "592450", "name": "Bryce Harper", "dfs_points": 14.5}],
    })
    points = load_actual_hitter_points(DATE, results_root=tmp_path)
    assert points == {"592450": 14.5}


def test_independent_hitter_projections_reads_latest_batter_board(tmp_path):
    _write(tmp_path / DATE / "batter_board_20260813T190000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T19:00:00Z",
        "hitters": [{"player_id": "592450", "name": "Bryce Harper", "projection": 9.2}],
    })
    points, path = load_independent_hitter_projections(DATE, predictions_root=tmp_path)
    assert points == {"592450": 9.2}
    assert path is not None


def test_external_and_adjusted_hitter_filters_to_hitters_only(tmp_path):
    doc = _adjusted_snapshot_doc([
        {"independent_player_id": "608331", "player_type": "pitcher", "external_projection": 19.9, "adjusted_projection": 20.2},
        {"independent_player_id": "592450", "player_type": "hitter", "external_projection": 8.5, "adjusted_projection": 9.0},
    ])
    save_adjusted_snapshot(doc, output_root=tmp_path)

    external, adjusted, _ = load_external_and_adjusted_hitter_projections(DATE, adjusted_root=tmp_path)
    assert external == {"592450": 8.5}
    assert adjusted == {"592450": 9.0}


def test_ai_hitter_projections_filters_to_hitters_only(tmp_path):
    doc = {
        "slate_date": DATE, "generated_at": f"{DATE}T21:00:00+00:00",
        "players": [
            {"player_id": "608331", "player_type": "pitcher", "ai_projection": 20.5},
            {"player_id": "592450", "player_type": "hitter", "ai_projection": 9.5},
        ],
    }
    save_ai_projection_snapshot(doc, output_root=tmp_path)

    points, _ = load_ai_hitter_projections(DATE, ai_root=tmp_path)
    assert points == {"592450": 9.5}


# ----------------------------------------------------------------------------
# build_*_projection_sources including native
# ----------------------------------------------------------------------------


def test_build_pitcher_sources_includes_native_when_present(tmp_path):
    native_root = tmp_path / "native"
    doc = _native_document([_native_player("608331", "pitcher", 21.0)])
    save_native_projection_document(doc, output_root=native_root)

    sources = build_pitcher_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=native_root,
    )
    assert sources == {"native": {"608331": 21.0}}


def test_build_hitter_sources_omits_missing_sources_entirely(tmp_path):
    sources = build_hitter_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=tmp_path / "native",
    )
    assert sources == {}


def test_build_hitter_sources_includes_only_whats_present(tmp_path):
    predictions_root = tmp_path / "predictions"
    native_root = tmp_path / "native"
    _write(predictions_root / DATE / "batter_board_20260813T180000.json", {
        "slate_date": DATE, "generated_at": f"{DATE}T18:00:00Z",
        "hitters": [{"player_id": "592450", "name": "Bryce Harper", "projection": 9.2}],
    })
    save_native_projection_document(_native_document([_native_player("592450", "hitter", 9.6)]), output_root=native_root)

    sources = build_hitter_projection_sources(
        DATE, predictions_root=predictions_root, adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=native_root,
    )
    assert sources == {"independent": {"592450": 9.2}, "native": {"592450": 9.6}}
    assert "external" not in sources
    assert "adjusted" not in sources
    assert "ai" not in sources
