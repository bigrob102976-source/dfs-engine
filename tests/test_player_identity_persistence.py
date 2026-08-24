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


def test_load_crosswalk_returns_empty_when_no_version_exists(tmp_path):
    assert load_crosswalk(output_root=tmp_path / "nope") == {}


def test_save_and_load_crosswalk_round_trips(tmp_path):
    root = tmp_path / "crosswalk"
    save_crosswalk({"1": _identity()}, "2026-08-23T18:00:00+00:00", output_root=root)

    loaded = load_crosswalk(output_root=root)
    assert "1" in loaded
    assert loaded["1"].canonical_name == "Test Player"
    assert loaded["1"].current_team == "NYY"


def test_save_crosswalk_writes_a_new_version_rather_than_overwriting(tmp_path):
    # Milestone 33.2: the crosswalk changed from a single mutable file to
    # immutable versioned snapshots (see player_identity/persistence.py's
    # module docstring) -- a second save must not destroy the first
    # version, and "latest" must resolve to the newest one.
    root = tmp_path / "crosswalk"
    first_path = save_crosswalk({"1": _identity(team="NYY")}, "2026-08-23T18:00:00+00:00", output_root=root)
    second_path = save_crosswalk({"1": _identity(team="BOS")}, "2026-08-23T19:00:00+00:00", output_root=root)

    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()

    loaded = load_crosswalk(output_root=root)
    assert loaded["1"].current_team == "BOS"  # latest version wins

    first_version = load_crosswalk(first_path)
    assert first_version["1"].current_team == "NYY"  # earlier version untouched


def test_save_crosswalk_never_collides_within_the_same_second(tmp_path):
    # The nonce suffix (not just the timestamp) is what makes two
    # refreshes racing in the same second each get a distinct filename --
    # this is the concurrency-safety property Milestone 33.0's audit
    # flagged as the highest shared-file risk in the codebase.
    root = tmp_path / "crosswalk"
    same_second = "2026-08-23T18:00:00+00:00"
    path_a = save_crosswalk({"1": _identity(mlb_id="1")}, same_second, output_root=root)
    path_b = save_crosswalk({"2": _identity(mlb_id="2")}, same_second, output_root=root)

    assert path_a != path_b
    assert path_a.exists() and path_b.exists()


def test_two_concurrent_refreshes_from_the_same_base_never_corrupt_or_lose_either_version(tmp_path):
    # Simulates two workers both reading version N, then both writing
    # their own successor derived from it -- proves neither write is
    # silently lost or corrupted, and "latest" always resolves to a
    # complete, valid document (never a half-written/interleaved one).
    root = tmp_path / "crosswalk"
    base_path = save_crosswalk({"1": _identity(mlb_id="1", team="NYY")}, "2026-08-23T18:00:00+00:00", output_root=root)
    base = load_crosswalk(base_path)

    worker_a_result = merge_crosswalk(base, [_identity(mlb_id="2", team="BOS")])
    worker_b_result = merge_crosswalk(base, [_identity(mlb_id="3", team="TB")])

    path_a = save_crosswalk(worker_a_result, "2026-08-23T18:00:05+00:00", output_root=root)
    path_b = save_crosswalk(worker_b_result, "2026-08-23T18:00:05+00:00", output_root=root)

    assert path_a != path_b
    # Both versions remain fully readable -- neither worker's write
    # clobbered the other's file.
    version_a = load_crosswalk(path_a)
    version_b = load_crosswalk(path_b)
    assert set(version_a.keys()) == {"1", "2"}
    assert set(version_b.keys()) == {"1", "3"}

    # "Latest" resolves deterministically to exactly one of the two
    # (whichever sorts last), never a mix/corruption of both.
    latest = load_crosswalk(output_root=root)
    assert latest.keys() in ({"1", "2"}, {"1", "3"})


def test_load_crosswalk_returns_empty_on_corrupt_file(tmp_path):
    root = tmp_path / "crosswalk"
    root.mkdir(parents=True)
    bad_path = root / "crosswalk_20260823T180000_deadbeef.json"
    bad_path.write_text("not valid json{{{", encoding="utf-8")
    assert load_crosswalk(bad_path) == {}


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
