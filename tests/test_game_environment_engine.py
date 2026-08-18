import json
from pathlib import Path

import pytest

from research.game_environment.engine import GameEnvironmentEngineError, build_slate_environment_report


def _write_research_package(root: Path, date: str, game_count: int = 2):
    folder = root / date
    folder.mkdir(parents=True)
    games = []
    teams_used = [("PHI", "COL"), ("NYY", "BOS"), ("SF", "LAD")]
    for i in range(game_count):
        home, away = teams_used[i % len(teams_used)]
        games.append({
            "game_id": f"g{i + 1}", "date": date, "game_datetime_utc": "2026-08-13T23:05:00Z", "status": "scheduled",
            "home_team_id": "1", "home_team_abbr": home, "away_team_id": "2", "away_team_abbr": away,
            "venue_id": "v1", "venue_name": "Test Park", "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
            "game_number": 1,
        })
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text("[]", encoding="utf-8")
    (folder / "pitchers.json").write_text("[]", encoding="utf-8")


def test_raises_a_clear_error_when_no_research_package_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_UMPIRE_PROVIDER", raising=False)
    with pytest.raises(GameEnvironmentEngineError):
        build_slate_environment_report("2026-08-13", research_output_root=str(tmp_path / "research_output"))


def test_builds_a_report_for_every_game_on_the_slate(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    monkeypatch.delenv("GAME_ENVIRONMENT_UMPIRE_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=3)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    assert report.slate_date == "2026-08-13"
    assert len(report.games) == 3
    assert report.generated_at
    assert report.engine_version == "0.1.0"


def test_every_game_has_a_score_and_summary(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    for game in report.games:
        assert 0.0 <= game.environment_score.overall <= 100.0
        assert game.summary.headline


def test_vegas_slate_analysis_is_computed_across_every_game(tmp_path, monkeypatch):
    # Milestone 24: Vegas no longer defaults to mock (unlike weather/bullpen),
    # so this test -- which specifically exercises Vegas slate analysis --
    # must explicitly opt into mock mode.
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.setenv("GAME_ENVIRONMENT_PROVIDER", "mock")
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=3)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    assert report.vegas_slate_analysis is not None
    assert report.vegas_slate_analysis.highest_total_game_id in {g.game_id for g in report.games}


def test_vegas_is_none_for_every_game_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    assert all(g.vegas is None for g in report.games)
    assert report.vegas_slate_analysis is None


def test_umpire_defaults_to_unknown_for_every_game(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_UMPIRE_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    for game in report.games:
        assert game.umpire.status == "UNKNOWN"


def test_report_serializes_cleanly_to_json(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))
    json.dumps(report.to_dict())  # must not raise


def test_report_has_no_validation_warnings_for_a_clean_slate(tmp_path, monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))
    assert report.warnings == []


def test_mlb_game_status_from_research_package_flows_through_to_each_game(tmp_path, monkeypatch):
    # Milestone 25: research_output/<date>/games.json's "status" field
    # (already collected, previously discarded before reaching
    # GameEnvironmentReport) must now flow through end to end.
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-13", game_count=2)  # fixture uses "status": "scheduled"

    report = build_slate_environment_report("2026-08-13", research_output_root=str(root))

    for game in report.games:
        assert game.mlb_game_status == "scheduled"
        assert game.game_status == "PREGAME"
