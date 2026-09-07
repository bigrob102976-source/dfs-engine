"""NFL M6A -- targeted tests for historical_nfl/raw_persistence.py.
tmp_path pattern mirrors tests/test_nfl_persistence.py (M2) and
tests/test_nfl_game_context_persistence.py (M5) exactly."""

import datetime
import json

import polars as pl
import pytest

from historical_nfl.raw_contract import DATASET_ROSTERS, DATASET_SCHEDULES, SCHEMA_VERSION, SOURCE, SPORT, NflverseRawSnapshotMetadata
from historical_nfl.raw_persistence import list_raw_snapshots, load_latest_raw_snapshot, save_raw_snapshot

SEASON = 2025
WEEK = 1
TS = "20260831T000000000000"


def _metadata(dataset_name, season=SEASON, week=None):
    return NflverseRawSnapshotMetadata(
        sport=SPORT, source=SOURCE, source_provenance="nflreadpy==0.1.5 test", dataset_name=dataset_name,
        season=season, week=week, fetched_at="2026-08-31T00:00:00+00:00", data_timestamp=None,
        event_time=None, available_at=None, ingested_at="2026-08-31T00:00:00+00:00",
        schema_version=SCHEMA_VERSION, row_count=1,
    )


def test_save_schedules_writes_season_only_scoped_path(tmp_path):
    df = pl.DataFrame({"game_id": ["g1"]})
    path = save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), TS, output_root=tmp_path)
    assert path == tmp_path / "schedules" / str(SEASON) / f"nflverse_schedules_{TS}.json"
    assert path.exists()


def test_save_rosters_writes_season_and_week_scoped_path(tmp_path):
    df = pl.DataFrame({"gsis_id": ["00-0000001"]})
    path = save_raw_snapshot(DATASET_ROSTERS, SEASON, WEEK, df, _metadata(DATASET_ROSTERS, week=WEEK), TS, output_root=tmp_path)
    assert path == tmp_path / "rosters" / str(SEASON) / str(WEEK) / f"nflverse_rosters_{TS}.json"


def test_week_grain_dataset_requires_week():
    df = pl.DataFrame({"gsis_id": ["00-0000001"]})
    with pytest.raises(ValueError):
        save_raw_snapshot(DATASET_ROSTERS, SEASON, None, df, _metadata(DATASET_ROSTERS), TS, output_root="ignored")


def test_save_never_overwrites(tmp_path):
    df = pl.DataFrame({"game_id": ["g1"]})
    save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), TS, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), TS, output_root=tmp_path)


def test_two_different_timestamps_both_persist_immutably(tmp_path):
    df = pl.DataFrame({"game_id": ["g1"]})
    save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), "20260831T000000000000", output_root=tmp_path)
    save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), "20260831T000001000000", output_root=tmp_path)
    assert len(list_raw_snapshots(DATASET_SCHEDULES, SEASON, output_root=tmp_path)) == 2


def test_load_latest_round_trips_metadata_and_rows(tmp_path):
    df = pl.DataFrame({"game_id": ["g1"], "home_team": ["PHI"]})
    save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, df, _metadata(DATASET_SCHEDULES), TS, output_root=tmp_path)
    loaded = load_latest_raw_snapshot(DATASET_SCHEDULES, SEASON, output_root=tmp_path)
    assert loaded["metadata"]["sport"] == "NFL"
    assert loaded["metadata"]["source"] == "NFLVERSE"
    assert loaded["rows"] == [{"game_id": "g1", "home_team": "PHI"}]


def test_load_latest_returns_none_when_nothing_saved(tmp_path):
    assert load_latest_raw_snapshot(DATASET_SCHEDULES, SEASON, output_root=tmp_path) is None


def test_rosters_scoped_to_week_not_leaking_across_weeks(tmp_path):
    df = pl.DataFrame({"gsis_id": ["00-0000001"]})
    save_raw_snapshot(DATASET_ROSTERS, SEASON, 1, df, _metadata(DATASET_ROSTERS, week=1), TS, output_root=tmp_path)
    assert len(list_raw_snapshots(DATASET_ROSTERS, SEASON, week=1, output_root=tmp_path)) == 1
    assert len(list_raw_snapshots(DATASET_ROSTERS, SEASON, week=2, output_root=tmp_path)) == 0


def test_date_and_datetime_columns_serialize_without_error(tmp_path):
    """Real nflverse rosters carry a `birth_date` (polars Date) column --
    Python's json module cannot encode that type natively; this must not
    crash, and must not silently drop or alter the underlying value."""
    df = pl.DataFrame({
        "gsis_id": ["00-0000001"],
        "birth_date": [datetime.date(1999, 3, 14)],
        "some_datetime": [datetime.datetime(2025, 9, 4, 17, 0, 0)],
    })
    path = save_raw_snapshot(DATASET_ROSTERS, SEASON, WEEK, df, _metadata(DATASET_ROSTERS, week=WEEK), TS, output_root=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["rows"][0]["birth_date"] == "1999-03-14"
    assert saved["rows"][0]["some_datetime"].startswith("2025-09-04")


def test_null_date_column_serializes_as_null(tmp_path):
    df = pl.DataFrame({"gsis_id": ["00-0000001"], "birth_date": [None]}, schema_overrides={"birth_date": pl.Date})
    path = save_raw_snapshot(DATASET_ROSTERS, SEASON, WEEK, df, _metadata(DATASET_ROSTERS, week=WEEK), TS, output_root=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["rows"][0]["birth_date"] is None
