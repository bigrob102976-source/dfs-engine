"""NFL M5 -- targeted tests for nfl/game_context_persistence.py. Mirrors
tests/test_nfl_persistence.py's (M2) tmp_path pattern."""

import pytest

from nfl.game_context_models import NflGameContext
from nfl.game_context_persistence import (
    list_nfl_game_context_snapshots,
    load_latest_nfl_game_context_snapshot,
    save_nfl_game_context_snapshot,
)

DG_ID = 151307
DATE = "2026-09-13"


def _games():
    return [NflGameContext(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, canonical_game_id="100", draftkings_game_id="100",
        home_team="PHI", away_team="DAL", spread=-3.0, total=47.5,
    )]


def test_save_writes_to_date_and_draft_group_scoped_path(tmp_path):
    path = save_nfl_game_context_snapshot(_games(), DATE, DG_ID, "20260913T120000", output_root=tmp_path)
    assert path == tmp_path / DATE / str(DG_ID) / "nfl_game_context_20260913T120000.json"
    assert path.exists()


def test_save_never_overwrites(tmp_path):
    save_nfl_game_context_snapshot(_games(), DATE, DG_ID, "20260913T120000", output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_nfl_game_context_snapshot(_games(), DATE, DG_ID, "20260913T120000", output_root=tmp_path)


def test_load_latest_round_trips(tmp_path):
    save_nfl_game_context_snapshot(_games(), DATE, DG_ID, "20260913T120000", output_root=tmp_path)
    loaded = load_latest_nfl_game_context_snapshot(DATE, DG_ID, output_root=tmp_path)
    assert loaded["sport"] == "NFL"
    assert loaded["draft_group_id"] == DG_ID
    assert loaded["games"][0]["spread"] == -3.0


def test_load_latest_returns_none_when_nothing_saved(tmp_path):
    assert load_latest_nfl_game_context_snapshot(DATE, DG_ID, output_root=tmp_path) is None


def test_scoped_to_draft_group_not_just_date(tmp_path):
    save_nfl_game_context_snapshot(_games(), DATE, DG_ID, "20260913T120000", output_root=tmp_path)
    assert len(list_nfl_game_context_snapshots(DATE, DG_ID, output_root=tmp_path)) == 1
    assert len(list_nfl_game_context_snapshots(DATE, 999999, output_root=tmp_path)) == 0
