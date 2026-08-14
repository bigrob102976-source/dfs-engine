import json
from pathlib import Path

import pytest

from external_projections.base import ProjectionProviderUnavailableError
from external_projections.mock_provider import MockExternalProvider, _mock_multiplier


def _write_research_package(root: Path, date: str):
    folder = root / date
    folder.mkdir(parents=True)
    games = [{
        "game_id": "g1", "date": date, "game_datetime_utc": "2026-08-11T23:05:00Z", "status": "scheduled",
        "home_team_id": "1", "home_team_abbr": "BOS", "away_team_id": "2", "away_team_abbr": "TOR",
        "venue_id": "v1", "venue_name": "Fenway", "home_probable_pitcher_id": "p2", "away_probable_pitcher_id": "p1",
        "game_number": 1,
    }]
    teams = [
        {"team_id": "1", "abbreviation": "BOS", "name": "Boston Red Sox"},
        {"team_id": "2", "abbreviation": "TOR", "name": "Toronto Blue Jays"},
    ]
    pitchers = [
        {"player_id": "p1", "name": "Away Ace", "team_id": "2", "team_abbr": "TOR", "opponent_team_id": "1",
         "opponent_abbr": "BOS", "game_id": "g1", "throws": "R", "status": "probable", "source": "mlb_stats_api"},
    ]
    batters = [
        {"player_id": "h1", "name": "Leadoff Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1, "position": "CF", "bats": "L",
         "status": "starting_lineup", "source": "mlb_stats_api"},
    ]
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps(pitchers), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps(batters), encoding="utf-8")


def _write_pitcher_snapshot(root: Path, date: str, timestamp: str = "20260811T180000"):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "slate_date": date, "generated_at": "2026-08-11T18:00:00+00:00", "model_version": "0.6.0",
        "pitchers": [{"player_id": "p1", "name": "Away Ace", "team": "TOR", "opponent": "BOS",
                      "projection": 20.0, "ceiling": 32.0, "floor": 8.0, "overall_score": 90.0, "confidence": 80.0}],
    }
    (folder / f"pitcher_board_{timestamp}.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_batter_snapshot(root: Path, date: str, timestamp: str = "20260811T180000"):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "slate_date": date, "generated_at": "2026-08-11T18:00:00+00:00", "model_version": "0.1.0",
        "hitters": [{"player_id": "h1", "name": "Leadoff Hitter", "team": "BOS", "opponent": "TOR",
                     "position": "CF", "projection": 10.0, "ceiling": 18.0, "floor": 4.0, "confidence": 60.0}],
    }
    (folder / f"batter_board_{timestamp}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_mock_provider_is_always_configured():
    assert MockExternalProvider().is_configured() is True


def test_mock_provider_name_is_clearly_labeled():
    assert MockExternalProvider().provider_name() == "MOCK EXTERNAL PROJECTIONS"


def test_mock_provider_never_claims_to_be_bluecollar():
    assert "bluecollar" not in MockExternalProvider().provider_name().lower()
    assert "blue collar" not in MockExternalProvider().provider_name().lower()


def test_mock_list_slates_uses_real_research_identity(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11")
    provider = MockExternalProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    slates = provider.list_slates("2026-08-11")
    assert len(slates) == 1
    assert slates[0].slate_id == "mock-external-2026-08-11"


def test_mock_list_slates_raises_unavailable_without_research_package(tmp_path):
    provider = MockExternalProvider(research_output_root=str(tmp_path / "research_output"), predictions_root=str(tmp_path / "predictions"))
    with pytest.raises(ProjectionProviderUnavailableError):
        provider.list_slates("2026-08-11")


def test_mock_get_projections_builds_real_identity_with_perturbed_projection(tmp_path):
    root = tmp_path / "research_output"
    predictions = tmp_path / "predictions"
    _write_research_package(root, "2026-08-11")
    _write_pitcher_snapshot(predictions, "2026-08-11")
    _write_batter_snapshot(predictions, "2026-08-11")
    provider = MockExternalProvider(research_output_root=str(root), predictions_root=str(predictions))

    players = provider.get_projections("mock-external-2026-08-11")
    by_name = {p.name: p for p in players}
    assert set(by_name) == {"Away Ace", "Leadoff Hitter"}

    ace = by_name["Away Ace"]
    assert ace.team == "TOR"
    assert ace.provider_name == "MOCK EXTERNAL PROJECTIONS"
    assert ace.projection != 20.0  # perturbed, not a passthrough
    assert 20.0 * 0.85 <= ace.projection <= 20.0 * 1.15  # within the documented +/-12% band (with rounding slack)


def test_mock_projection_perturbation_is_deterministic_not_random(tmp_path):
    root = tmp_path / "research_output"
    predictions = tmp_path / "predictions"
    _write_research_package(root, "2026-08-11")
    _write_pitcher_snapshot(predictions, "2026-08-11")
    _write_batter_snapshot(predictions, "2026-08-11")
    provider = MockExternalProvider(research_output_root=str(root), predictions_root=str(predictions))

    first = {p.name: p.projection for p in provider.get_projections("mock-external-2026-08-11")}
    second = {p.name: p.projection for p in provider.get_projections("mock-external-2026-08-11")}
    assert first == second


def test_mock_multiplier_is_bounded():
    for pid in ("p1", "h1", "some-other-id", "12345"):
        m = _mock_multiplier(pid)
        assert 0.88 <= m <= 1.12


def test_mock_get_projections_raises_unavailable_without_any_snapshot(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11")
    provider = MockExternalProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    with pytest.raises(ProjectionProviderUnavailableError):
        provider.get_projections("mock-external-2026-08-11")
