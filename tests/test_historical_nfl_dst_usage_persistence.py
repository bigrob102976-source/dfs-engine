"""NFL M8 -- targeted tests for historical_nfl/dst_usage_persistence.py."""

import pytest

from historical_nfl.dst_usage_models import NflDstUsageRecord
from historical_nfl.dst_usage_persistence import list_dst_usage_snapshots, load_latest_dst_usage_snapshot, save_dst_usage_snapshot

SEASON, WEEK = 2025, 1
TS = "20260904T000000000000"


def _record():
    return NflDstUsageRecord(team="PHI", opponent="DAL", season=SEASON, week=WEEK, game_id="g1", sacks=2.0, interceptions=1)


def test_save_writes_season_and_week_scoped_path(tmp_path):
    path = save_dst_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    assert path == tmp_path / str(SEASON) / str(WEEK) / f"nfl_dst_usage_{TS}.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_dst_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_dst_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)


def test_load_latest_round_trips(tmp_path):
    save_dst_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    loaded = load_latest_dst_usage_snapshot(SEASON, WEEK, output_root=tmp_path)
    assert loaded["row_count"] == 1
    assert loaded["records"][0]["team"] == "PHI"


def test_load_latest_none_when_nothing_saved(tmp_path):
    assert load_latest_dst_usage_snapshot(SEASON, WEEK, output_root=tmp_path) is None
