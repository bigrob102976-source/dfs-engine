"""NFL M6C -- targeted tests for historical_nfl/usage_persistence.py.
Mirrors tests/test_historical_nfl_raw_persistence.py's tmp_path pattern."""

import pytest

from historical_nfl.usage_models import NflUsageRecord
from historical_nfl.usage_persistence import list_usage_snapshots, load_latest_usage_snapshot, save_usage_snapshot

SEASON, WEEK = 2025, 1
TS = "20260831T000000000000"


def _record(gsis_id="00-1"):
    return NflUsageRecord(canonical_player_id=f"gsis:{gsis_id}", gsis_id=gsis_id, season=SEASON, week=WEEK, game_id="g1", team="PHI", opponent="DAL", position="WR")


def test_save_writes_season_and_week_scoped_path(tmp_path):
    path = save_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    assert path == tmp_path / str(SEASON) / str(WEEK) / f"nfl_usage_{TS}.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)


def test_load_latest_round_trips(tmp_path):
    save_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=tmp_path)
    loaded = load_latest_usage_snapshot(SEASON, WEEK, output_root=tmp_path)
    assert loaded["row_count"] == 1
    assert loaded["records"][0]["gsis_id"] == "00-1"


def test_load_latest_none_when_nothing_saved(tmp_path):
    assert load_latest_usage_snapshot(SEASON, WEEK, output_root=tmp_path) is None


def test_scoped_to_week_not_leaking_across_weeks(tmp_path):
    save_usage_snapshot([_record()], SEASON, 1, TS, output_root=tmp_path)
    assert len(list_usage_snapshots(SEASON, 1, output_root=tmp_path)) == 1
    assert len(list_usage_snapshots(SEASON, 2, output_root=tmp_path)) == 0


def test_never_touches_m6a_raw_directory(tmp_path):
    """M6A raw snapshots live under raw/nflverse/...; normalized usage
    must be a fully separate tree under the same tmp_path root."""
    from historical_nfl.raw_persistence import save_raw_snapshot
    from historical_nfl.raw_contract import DATASET_SCHEDULES, NflverseRawSnapshotMetadata, SCHEMA_VERSION, SOURCE, SPORT
    import polars as pl

    raw_root = tmp_path / "raw" / "nflverse"
    metadata = NflverseRawSnapshotMetadata(
        sport=SPORT, source=SOURCE, source_provenance="test", dataset_name=DATASET_SCHEDULES, season=SEASON,
        week=None, fetched_at="t0", data_timestamp=None, event_time=None, available_at=None, ingested_at="t0",
        schema_version=SCHEMA_VERSION, row_count=1,
    )
    save_raw_snapshot(DATASET_SCHEDULES, SEASON, None, pl.DataFrame({"game_id": ["g1"]}), metadata, TS, output_root=raw_root)
    normalized_root = tmp_path / "normalized" / "usage"
    save_usage_snapshot([_record()], SEASON, WEEK, TS, output_root=normalized_root)

    assert (raw_root / "schedules" / str(SEASON) / f"nflverse_schedules_{TS}.json").exists()
    assert (normalized_root / str(SEASON) / str(WEEK) / f"nfl_usage_{TS}.json").exists()
