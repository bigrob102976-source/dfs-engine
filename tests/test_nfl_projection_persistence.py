"""NFL M4 -- targeted tests for nfl/projection_persistence.py. Mirrors
tests/test_nfl_persistence.py's (M2) tmp_path pattern."""

import pytest

from nfl.projection_models import BIG_MONEY_NATIVE, NflProjectionRecord, NflProjectionSnapshot, NflProjectionValidationResult
from nfl.projection_persistence import list_nfl_projection_snapshots, load_latest_nfl_projection_snapshot, save_nfl_projection_snapshot

DG_ID = 151307
DATE = "2026-09-13"


def _record(projection=18.5):
    return NflProjectionRecord(
        sport="NFL", draft_group_id=DG_ID, canonical_player_id="1", draftkings_player_id="1", draftable_ids=["10"],
        name="QB One", position="QB", team="BUF", opponent="HOU", projection=projection,
    )


def _snapshot():
    validation = NflProjectionValidationResult(passed=True, total_pool_players=1, projected_players=1, missing_players=0, match_rate=1.0, position_projected_counts={"QB": 1})
    return NflProjectionSnapshot(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, source=BIG_MONEY_NATIVE, source_provenance=BIG_MONEY_NATIVE,
        generated_at="2026-09-13T12:00:00Z", model_name="test-model", model_version="v0", records=[_record()], validation=validation,
    )


def test_save_writes_to_sport_and_source_scoped_path(tmp_path):
    path = save_nfl_projection_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    assert path == tmp_path / DATE / str(DG_ID) / "nfl_projection_20260913T120000.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_nfl_projection_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_nfl_projection_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)


def test_load_latest_round_trips_none_and_real_values(tmp_path):
    save_nfl_projection_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    loaded = load_latest_nfl_projection_snapshot(DATE, DG_ID, output_root=tmp_path)
    assert loaded["source_provenance"] == BIG_MONEY_NATIVE
    assert loaded["records"][0]["projection"] == 18.5
    assert loaded["validation"]["passed"] is True


def test_load_latest_returns_none_when_nothing_saved(tmp_path):
    assert load_latest_nfl_projection_snapshot(DATE, DG_ID, output_root=tmp_path) is None


def test_list_scoped_to_draft_group(tmp_path):
    save_nfl_projection_snapshot(_snapshot(), "20260913T120000", output_root=tmp_path)
    assert len(list_nfl_projection_snapshots(DATE, DG_ID, output_root=tmp_path)) == 1
    assert len(list_nfl_projection_snapshots(DATE, 999999, output_root=tmp_path)) == 0
