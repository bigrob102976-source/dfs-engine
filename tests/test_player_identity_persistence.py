import pytest

from player_identity.models import CanonicalIdentity
from player_identity.persistence import (
    load_crosswalk,
    merge_crosswalk,
    save_crosswalk,
    save_identity_refresh_snapshot,
)


def _identity(mlb_id="1", team="NYY", verified="2026-08-23T18:00:00+00:00"):
    return CanonicalIdentity(
        mlb_player_id=mlb_id, canonical_name="Test Player", normalized_name="test player",
        current_team=team, position="OF", player_type="hitter", last_verified_at=verified,
    )


def test_save_identity_refresh_snapshot_is_immutable(tmp_path):
    path = save_identity_refresh_snapshot({"teams_total": 1}, "2026-08-23", "20260823T180000", output_root=tmp_path)
    assert path.exists()
    with pytest.raises(FileExistsError):
        save_identity_refresh_snapshot({"teams_total": 1}, "2026-08-23", "20260823T180000", output_root=tmp_path)


def test_load_crosswalk_returns_empty_when_file_does_not_exist(tmp_path):
    assert load_crosswalk(tmp_path / "nope.json") == {}


def test_save_and_load_crosswalk_round_trips(tmp_path):
    path = tmp_path / "crosswalk.json"
    save_crosswalk({"1": _identity()}, "2026-08-23T18:00:00+00:00", path=path)

    loaded = load_crosswalk(path)
    assert "1" in loaded
    assert loaded["1"].canonical_name == "Test Player"
    assert loaded["1"].current_team == "NYY"


def test_save_crosswalk_overwrites_the_previous_version(tmp_path):
    path = tmp_path / "crosswalk.json"
    save_crosswalk({"1": _identity(team="NYY")}, "2026-08-23T18:00:00+00:00", path=path)
    save_crosswalk({"1": _identity(team="BOS")}, "2026-08-23T19:00:00+00:00", path=path)

    loaded = load_crosswalk(path)
    assert loaded["1"].current_team == "BOS"  # rolling file -- overwritten, not appended/immutable


def test_load_crosswalk_returns_empty_on_corrupt_file(tmp_path):
    path = tmp_path / "crosswalk.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    assert load_crosswalk(path) == {}


def test_merge_crosswalk_adds_new_players():
    existing = {"1": _identity(mlb_id="1")}
    merged = merge_crosswalk(existing, [_identity(mlb_id="2")])
    assert set(merged.keys()) == {"1", "2"}


def test_merge_crosswalk_newest_fetch_always_wins_for_current_team():
    existing = {"1": _identity(mlb_id="1", team="BOS", verified="2026-08-22T18:00:00+00:00")}
    merged = merge_crosswalk(existing, [_identity(mlb_id="1", team="NYY", verified="2026-08-23T18:00:00+00:00")])
    assert merged["1"].current_team == "NYY"


def test_merge_crosswalk_keeps_players_not_reobserved_today():
    existing = {"1": _identity(mlb_id="1"), "2": _identity(mlb_id="2")}
    merged = merge_crosswalk(existing, [_identity(mlb_id="1")])  # team 2's roster fetch failed today
    assert "2" in merged
    assert merged["2"].current_team == "NYY"  # unchanged, still useful
