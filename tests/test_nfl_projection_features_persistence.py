"""NFL M8 -- targeted tests for nfl/projection_features_persistence.py."""

import pytest

from nfl.projection_features import NflProjectionFeatures
from nfl.projection_features_persistence import (
    list_projection_features_snapshots,
    load_latest_projection_features_snapshot,
    save_projection_features_snapshot,
)

SEASON, WEEK = 2025, 6
TS = "20260904T000000000000"


def _feature():
    return NflProjectionFeatures(
        canonical_player_id="gsis:00-1", draftkings_player_id="1", gsis_id="00-1",
        position="WR", team="PHI", opponent="DAL", salary=6000,
        feature_as_of_season=SEASON, feature_as_of_week=WEEK,
    )


def test_save_writes_season_and_week_scoped_path(tmp_path):
    path = save_projection_features_snapshot([_feature()], SEASON, WEEK, TS, output_root=tmp_path)
    assert path == tmp_path / str(SEASON) / str(WEEK) / f"nfl_projection_features_{TS}.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_projection_features_snapshot([_feature()], SEASON, WEEK, TS, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_projection_features_snapshot([_feature()], SEASON, WEEK, TS, output_root=tmp_path)


def test_load_latest_round_trips(tmp_path):
    save_projection_features_snapshot([_feature()], SEASON, WEEK, TS, output_root=tmp_path)
    loaded = load_latest_projection_features_snapshot(SEASON, WEEK, output_root=tmp_path)
    assert loaded["row_count"] == 1
    assert loaded["features"][0]["gsis_id"] == "00-1"


def test_load_latest_none_when_nothing_saved(tmp_path):
    assert load_latest_projection_features_snapshot(SEASON, WEEK, output_root=tmp_path) is None
