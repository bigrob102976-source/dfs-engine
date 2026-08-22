"""Milestone 32.2B -- ml_projection_snapshots persistence tests:
immutability, slate isolation, date isolation."""

import pytest

from big_money_ml.models import MLPitcherProjection, MLProjectionDocument
from big_money_ml.persistence import (
    list_ml_projection_snapshots,
    load_latest_ml_projection_snapshot,
    save_ml_projection_document,
)


def _document(slate_date, generated_at, projection=7.5):
    player = MLPitcherProjection(
        player_id="123", dk_player_id="dk123", name="Test Pitcher", team="NYY", opponent="BOS",
        game_id="g1", salary=9000, projection=projection, model_version="1.0.0",
        data_quality_score=0.95, feature_coverage=0.95, projection_status="LIVE_PREGAME",
    )
    return MLProjectionDocument(
        slate_date=slate_date, generated_at=generated_at, model_version="1.0.0", warehouse_version="mlb_feature_warehouse_v1",
        raw_dk_pitcher_count=1, starting_pitcher_count=1, ml_eligible_pitcher_count=1,
        ml_projections_generated=1, ml_projections_missing=0, feature_parity_summary={}, players=[player],
    )


def test_save_and_load_round_trips(tmp_path):
    doc = _document("2026-08-22", "2026-08-22T12:00:00+00:00")
    path = save_ml_projection_document(doc, output_root=tmp_path)
    assert path.exists()
    loaded = load_latest_ml_projection_snapshot("2026-08-22", output_root=tmp_path)
    assert loaded["players"][0]["projection"] == 7.5


def test_save_never_overwrites_an_existing_snapshot(tmp_path):
    doc = _document("2026-08-22", "2026-08-22T12:00:00+00:00")
    save_ml_projection_document(doc, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_ml_projection_document(doc, output_root=tmp_path)  # identical timestamp -> identical filename


def test_snapshots_are_isolated_by_slate_date(tmp_path):
    save_ml_projection_document(_document("2026-08-21", "2026-08-21T12:00:00+00:00", projection=5.0), output_root=tmp_path)
    save_ml_projection_document(_document("2026-08-22", "2026-08-22T12:00:00+00:00", projection=9.0), output_root=tmp_path)

    day1 = load_latest_ml_projection_snapshot("2026-08-21", output_root=tmp_path)
    day2 = load_latest_ml_projection_snapshot("2026-08-22", output_root=tmp_path)
    assert day1["players"][0]["projection"] == 5.0
    assert day2["players"][0]["projection"] == 9.0


def test_list_snapshots_returns_empty_for_a_date_with_no_snapshots(tmp_path):
    assert list_ml_projection_snapshots("2099-01-01", output_root=tmp_path) == []
    assert load_latest_ml_projection_snapshot("2099-01-01", output_root=tmp_path) is None


def test_list_snapshots_is_chronologically_sorted(tmp_path):
    save_ml_projection_document(_document("2026-08-22", "2026-08-22T12:00:00+00:00", projection=1.0), output_root=tmp_path)
    save_ml_projection_document(_document("2026-08-22", "2026-08-22T13:00:00+00:00", projection=2.0), output_root=tmp_path)
    snapshots = list_ml_projection_snapshots("2026-08-22", output_root=tmp_path)
    assert len(snapshots) == 2
    assert snapshots[0].name < snapshots[1].name

    latest = load_latest_ml_projection_snapshot("2026-08-22", output_root=tmp_path)
    assert latest["players"][0]["projection"] == 2.0  # the later-timestamped run wins "latest"


def test_document_never_carries_actual_dk_points_or_secrets():
    doc = _document("2026-08-22", "2026-08-22T12:00:00+00:00")
    d = doc.to_dict()
    serialized = str(d)
    for forbidden in ("actual_dk_points", "api_key", "API_KEY", "secret"):
        assert forbidden not in serialized
