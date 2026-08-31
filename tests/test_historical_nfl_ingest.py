"""NFL M6A -- targeted tests for historical_nfl/ingest.py's orchestration
(fetch -> validate -> persist wiring). nflverse_client's fetch functions
are monkeypatched -- no real network call here."""

import polars as pl
import pytest

from historical_nfl import ingest, nflverse_client
from historical_nfl.nflverse_client import NflverseUnavailableError

SEASON = 2025
WEEK = 1


def _schedules_df():
    return pl.DataFrame({
        "season": [SEASON], "week": [WEEK], "game_id": ["2025_01_DAL_PHI"],
        "home_team": ["PHI"], "away_team": ["DAL"], "gameday": ["2025-09-04"],
    })


def _patch_all_fetchers(monkeypatch, fetched_at="2026-08-31T00:00:00+00:00"):
    monkeypatch.setattr(nflverse_client, "fetch_schedules", lambda season: (_schedules_df(), fetched_at, "prov_schedules"))
    monkeypatch.setattr(nflverse_client, "fetch_rosters", lambda season, week=None: (
        pl.DataFrame({"season": [SEASON], "week": [WEEK], "gsis_id": ["00-0000001"], "full_name": ["Player One"], "team": ["PHI"], "position": ["QB"]}),
        fetched_at, "prov_rosters",
    ))
    monkeypatch.setattr(nflverse_client, "fetch_weekly_player_stats", lambda season, week=None: (
        pl.DataFrame({
            "season": [SEASON], "week": [WEEK], "player_id": ["00-0000001"], "team": ["PHI"], "position": ["QB"], "game_id": ["2025_01_DAL_PHI"],
            "completions": [20], "attempts": [30], "passing_yards": [250.0], "passing_tds": [2],
            "carries": [3], "rushing_yards": [10], "rushing_tds": [0],
            "receptions": [0], "targets": [0], "receiving_yards": [0], "receiving_tds": [0],
        }), fetched_at, "prov_weekly",
    ))
    monkeypatch.setattr(nflverse_client, "fetch_team_stats", lambda season, week=None: (
        pl.DataFrame({"season": [SEASON], "week": [WEEK], "team": ["PHI"], "opponent_team": ["DAL"]}), fetched_at, "prov_team",
    ))
    monkeypatch.setattr(nflverse_client, "fetch_play_by_play", lambda season, week=None: (
        pl.DataFrame({
            "game_id": ["2025_01_DAL_PHI"], "play_id": [1.0], "season": [SEASON], "week": [WEEK],
            "posteam": ["PHI"], "defteam": ["DAL"], "epa": [0.5], "yardline_100": [50.0], "down": [1.0], "ydstogo": [10.0],
        }), fetched_at, "prov_pbp",
    ))


def test_ingest_schedules_persists_and_reports_quality(monkeypatch, tmp_path):
    _patch_all_fetchers(monkeypatch)
    result = ingest.ingest_schedules(SEASON, output_root=tmp_path)
    assert result.dataset_name == "schedules"
    assert result.metadata["sport"] == "NFL"
    assert result.metadata["source"] == "NFLVERSE"
    assert result.quality_report["passed"] is True
    assert result.quality_report["row_count"] == 1


def test_ingest_rosters_requires_week_and_persists(monkeypatch, tmp_path):
    _patch_all_fetchers(monkeypatch)
    result = ingest.ingest_rosters(SEASON, WEEK, output_root=tmp_path)
    assert result.week == WEEK
    assert result.quality_report["missing_identity_count"] == 0


def test_ingest_week_runs_all_five_datasets(monkeypatch, tmp_path):
    _patch_all_fetchers(monkeypatch)
    results = ingest.ingest_week(SEASON, WEEK, output_root=tmp_path)
    assert set(results.keys()) == {"schedules", "rosters", "weekly_player_stats", "team_stats", "play_by_play"}
    for r in results.values():
        assert r.quality_report["passed"] is True


def test_ingest_propagates_network_failure_without_persisting(monkeypatch, tmp_path):
    def _boom(season):
        raise NflverseUnavailableError("simulated failure")

    monkeypatch.setattr(nflverse_client, "fetch_schedules", _boom)
    with pytest.raises(NflverseUnavailableError):
        ingest.ingest_schedules(SEASON, output_root=tmp_path)
    from historical_nfl.raw_persistence import list_raw_snapshots
    assert list_raw_snapshots("schedules", SEASON, output_root=tmp_path) == []


def test_ingest_empty_source_persists_zero_row_snapshot_not_an_error(monkeypatch, tmp_path):
    empty = pl.DataFrame({"season": [], "week": [], "game_id": [], "home_team": [], "away_team": [], "gameday": []})
    monkeypatch.setattr(nflverse_client, "fetch_schedules", lambda season: (empty, "2026-08-31T00:00:00+00:00", "prov"))
    result = ingest.ingest_schedules(SEASON, output_root=tmp_path)
    assert result.metadata["row_count"] == 0
    assert result.quality_report["passed"] is True


def test_two_ingests_of_same_dataset_never_collide(monkeypatch, tmp_path):
    _patch_all_fetchers(monkeypatch)
    ingest.ingest_schedules(SEASON, output_root=tmp_path)
    ingest.ingest_schedules(SEASON, output_root=tmp_path)  # a second, later immutable snapshot -- never an overwrite
    from historical_nfl.raw_persistence import list_raw_snapshots
    assert len(list_raw_snapshots("schedules", SEASON, output_root=tmp_path)) == 2
