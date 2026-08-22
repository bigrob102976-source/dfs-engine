"""Milestone 32.1, Part 8 -- player_crosswalk_builder.py. No network
calls (fetch_cached_person is monkeypatched)."""

from historical_mlb.player_crosswalk_builder import PlayerCrosswalkBuilder


def test_observe_new_player_creates_row(monkeypatch):
    monkeypatch.setattr(
        "historical_mlb.player_crosswalk_builder.fetch_cached_person",
        lambda pid: {"batSide": {"code": "R"}, "pitchHand": {"code": "L"}},
    )
    builder = PlayerCrosswalkBuilder()
    row = builder.observe("592450", "Aaron Judge", "NYY", "2025-06-15")
    assert row.mlbam_id == "592450"
    assert row.bat_side == "R"
    assert row.throw_side == "L"
    assert row.first_seen == "2025-06-15"
    assert row.last_seen == "2025-06-15"


def test_observe_same_player_twice_expands_first_last_seen(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "historical_mlb.player_crosswalk_builder.fetch_cached_person",
        lambda pid: (calls.append(pid), None)[1],
    )

    builder = PlayerCrosswalkBuilder()
    builder.observe("592450", "Aaron Judge", "NYY", "2025-06-15")
    builder.observe("592450", "Aaron Judge", "NYY", "2025-06-10")
    builder.observe("592450", "Aaron Judge", "NYY", "2025-06-20")

    row = builder.get("592450")
    assert row.first_seen == "2025-06-10"
    assert row.last_seen == "2025-06-20"
    assert len(calls) == 1  # fetch_cached_person only called ONCE ever for this player, not once per observation


def test_observe_updates_team_on_later_observation(monkeypatch):
    monkeypatch.setattr("historical_mlb.player_crosswalk_builder.fetch_cached_person", lambda pid: None)
    builder = PlayerCrosswalkBuilder()
    builder.observe("592450", "Aaron Judge", "NYY", "2025-06-10")
    builder.observe("592450", "Aaron Judge", "SF", "2025-08-01")  # traded
    row = builder.get("592450")
    assert row.team == "SF"  # most-recent team wins


def test_get_returns_none_for_unseen_player(monkeypatch):
    builder = PlayerCrosswalkBuilder()
    assert builder.get("999999") is None


def test_rows_returns_every_observed_player(monkeypatch):
    monkeypatch.setattr("historical_mlb.player_crosswalk_builder.fetch_cached_person", lambda pid: None)
    builder = PlayerCrosswalkBuilder()
    builder.observe("1", "A", "NYY", "2025-06-10")
    builder.observe("2", "B", "BOS", "2025-06-10")
    assert {r.mlbam_id for r in builder.rows()} == {"1", "2"}
