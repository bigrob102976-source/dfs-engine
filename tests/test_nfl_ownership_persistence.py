"""NFL M12 -- targeted tests for nfl/ownership_persistence.py. Mirrors
tests/test_nfl_projection_persistence.py's tmp_path pattern exactly."""

import pytest

from nfl.ownership_models import NflOwnershipRecord, NflOwnershipSnapshot, NflOwnershipValidationResult
from nfl.ownership_persistence import list_nfl_ownership_snapshots, load_latest_nfl_ownership_snapshot, save_nfl_ownership_snapshot

DG_ID = 151307
DATE = "2026-09-13"


def _record(ownership=42.0):
    return NflOwnershipRecord(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, draftkings_player_id="1", canonical_player_id="1",
        name="QB One", position="QB", team="BUF", opponent="HOU", ownership_projection=ownership, ownership_rank=1,
        source="BIG_MONEY_NATIVE_OWNERSHIP_V1", source_provenance="TEST_PROVENANCE",
        method="deterministic_estimator", model_version="nfl_ownership_v1", generated_at="2026-09-13T12:00:00Z",
    )


def _snapshot():
    validation = NflOwnershipValidationResult(
        passed=True, total_pool_players=1, players_with_ownership=1, players_missing_ownership=0,
        ownership_sum_by_position={"QB": 100.0}, ownership_expected_by_position={"QB": 100.0},
    )
    return NflOwnershipSnapshot(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, source="BIG_MONEY_NATIVE_OWNERSHIP_V1",
        source_provenance="TEST_PROVENANCE", method="deterministic_estimator", model_version="nfl_ownership_v1",
        generated_at="2026-09-13T12:00:00Z", records=[_record()], validation=validation,
        normalization_report={"total_expected_mass": 900.0},
    )


def test_save_writes_to_sport_and_draft_group_scoped_path(tmp_path):
    path = save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    assert path == tmp_path / DATE / str(DG_ID) / "nfl_ownership_20260913T120000.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)


def test_load_latest_round_trips_real_values(tmp_path):
    save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    loaded = load_latest_nfl_ownership_snapshot(DATE, DG_ID, output_root=tmp_path)
    assert loaded["source"] == "BIG_MONEY_NATIVE_OWNERSHIP_V1"
    assert loaded["method"] == "deterministic_estimator"
    assert loaded["model_version"] == "nfl_ownership_v1"
    assert loaded["records"][0]["ownership_projection"] == 42.0
    assert loaded["validation"]["passed"] is True
    assert loaded["normalization_report"]["total_expected_mass"] == 900.0


def test_load_latest_returns_none_when_nothing_saved(tmp_path):
    assert load_latest_nfl_ownership_snapshot(DATE, DG_ID, output_root=tmp_path) is None


def test_list_scoped_to_draft_group(tmp_path):
    save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    assert len(list_nfl_ownership_snapshots(DATE, DG_ID, output_root=tmp_path)) == 1
    assert len(list_nfl_ownership_snapshots(DATE, 999999, output_root=tmp_path)) == 0


def test_two_snapshots_same_run_never_collide(tmp_path):
    save_nfl_ownership_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    save_nfl_ownership_snapshot(_snapshot(), "20260913T130000", output_root=tmp_path)
    assert len(list_nfl_ownership_snapshots(DATE, DG_ID, output_root=tmp_path)) == 2
