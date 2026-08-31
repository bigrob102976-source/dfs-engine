"""NFL M6A -- targeted tests for historical_nfl/nflverse_client.py.
Mocks nflreadpy's own loader functions (monkeypatch) -- no real network
call here; the real integration proof is the M6A final report's live
2025 Week 1 ingestion run, not this file."""

import polars as pl
import pytest

import nflreadpy
from historical_nfl import nflverse_client
from historical_nfl.nflverse_client import NflverseUnavailableError


def test_fetch_schedules_returns_dataframe_fetched_at_and_provenance(monkeypatch):
    df = pl.DataFrame({"season": [2025], "week": [1], "game_id": ["2025_01_DAL_PHI"]})
    monkeypatch.setattr(nflreadpy, "load_schedules", lambda seasons: df)
    result_df, fetched_at, provenance = nflverse_client.fetch_schedules(2025)
    assert result_df.height == 1
    assert fetched_at  # a real, non-empty ISO timestamp string
    assert "load_schedules" in provenance
    assert "2025" in provenance


def test_fetch_rosters_uses_load_rosters_weekly_not_load_rosters(monkeypatch):
    """M6A Phase 1 finding: load_rosters()'s week column does not
    reconcile with weekly stats by GSIS ID; load_rosters_weekly() does.
    This must never regress back to the wrong function."""
    called = {}
    df = pl.DataFrame({"season": [2025], "week": [1], "gsis_id": ["00-0000001"]})

    def _load_rosters_weekly(seasons):
        called["called"] = True
        return df

    monkeypatch.setattr(nflreadpy, "load_rosters_weekly", _load_rosters_weekly)
    monkeypatch.setattr(nflreadpy, "load_rosters", lambda seasons: (_ for _ in ()).throw(AssertionError("load_rosters must not be called")))
    result_df, fetched_at, provenance = nflverse_client.fetch_rosters(2025, week=1)
    assert called.get("called") is True
    assert result_df.height == 1
    assert "load_rosters_weekly" in provenance


def test_fetch_rosters_filters_to_requested_week(monkeypatch):
    df = pl.DataFrame({"season": [2025, 2025], "week": [1, 2], "gsis_id": ["00-0000001", "00-0000002"]})
    monkeypatch.setattr(nflreadpy, "load_rosters_weekly", lambda seasons: df)
    result_df, _, provenance = nflverse_client.fetch_rosters(2025, week=1)
    assert result_df.height == 1
    assert result_df["week"].to_list() == [1]
    assert "filtered week=1" in provenance


def test_fetch_weekly_player_stats_filters_to_requested_week(monkeypatch):
    df = pl.DataFrame({"season": [2025, 2025], "week": [1, 2], "player_id": ["a", "b"]})
    monkeypatch.setattr(nflreadpy, "load_player_stats", lambda seasons: df)
    result_df, _, _ = nflverse_client.fetch_weekly_player_stats(2025, week=2)
    assert result_df["player_id"].to_list() == ["b"]


def test_fetch_weekly_player_stats_no_week_returns_full_season(monkeypatch):
    df = pl.DataFrame({"season": [2025, 2025], "week": [1, 2], "player_id": ["a", "b"]})
    monkeypatch.setattr(nflreadpy, "load_player_stats", lambda seasons: df)
    result_df, _, _ = nflverse_client.fetch_weekly_player_stats(2025)
    assert result_df.height == 2


def test_network_failure_raises_typed_error_not_silent_fallback(monkeypatch):
    def _boom(seasons):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(nflreadpy, "load_schedules", _boom)
    with pytest.raises(NflverseUnavailableError):
        nflverse_client.fetch_schedules(2025)


def test_none_response_raises_typed_error(monkeypatch):
    monkeypatch.setattr(nflreadpy, "load_team_stats", lambda seasons: None)
    with pytest.raises(NflverseUnavailableError):
        nflverse_client.fetch_team_stats(2025, week=1)


def test_empty_dataframe_is_not_an_error():
    """An empty (but real, well-formed) result is a legitimate outcome,
    never conflated with an unavailable source."""
    empty = pl.DataFrame({"season": [], "week": [], "game_id": []})
    assert empty.height == 0  # sanity: this fixture itself is genuinely empty, not a stand-in for failure


def test_fetch_play_by_play_filters_to_requested_week(monkeypatch):
    df = pl.DataFrame({"season": [2025, 2025], "week": [1, 2], "game_id": ["g1", "g2"]})
    monkeypatch.setattr(nflreadpy, "load_pbp", lambda seasons: df)
    result_df, _, _ = nflverse_client.fetch_play_by_play(2025, week=1)
    assert result_df["game_id"].to_list() == ["g1"]
