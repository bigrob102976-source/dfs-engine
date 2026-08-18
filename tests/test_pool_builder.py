import json
from pathlib import Path

import pytest

from dfs.models import DKSalaryRow
from dfs.pool_builder import build_pool, print_pool_report, save_pool
from dfs.providers.adapter import provider_players_to_dk_rows


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


def _dk_rows():
    return [
        DKSalaryRow(dk_player_id="d1", name="Away Ace", team_abbrev="TOR", dk_positions=["P"], salary=8000, game_info="TOR@BOS 7:05PM ET"),
        DKSalaryRow(dk_player_id="d2", name="Leadoff Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET"),
    ]


def test_build_pool_matches_real_identities(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")

    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    assert result.report["matched_to_mlb"] == 2
    # No pitcher/batter snapshot exists in this fixture -- matched players
    # correctly land as "missing_projection", not "active" (never invented).
    assert {p.name for p in result.players} == {"Away Ace", "Leadoff Hitter"}
    assert all(p.match_status == "matched" for p in result.players)
    assert all(p.lineup_status == "missing_projection" for p in result.players)


def test_build_pool_never_invents_projection_without_a_snapshot(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    assert all(p.projection is None for p in result.players)


def test_save_pool_is_immutable(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    dfs_input_root = tmp_path / "dfs_input"
    generated_at = "2026-08-11T18:00:00+00:00"
    pool_path, report_path = save_pool(result, "2026-08-11", str(dfs_input_root), generated_at=generated_at)
    assert pool_path.exists()
    assert report_path.exists()

    with pytest.raises(FileExistsError):
        save_pool(result, "2026-08-11", str(dfs_input_root), generated_at=generated_at)


def test_save_pool_records_extra_metadata(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    pool_path, _ = save_pool(
        result, "2026-08-11", str(tmp_path / "dfs_input"),
        extra_metadata={"provider_source": "mock_dev_provider", "selected_slate_id": "mock-main"},
        generated_at="2026-08-11T18:00:00+00:00",
    )
    doc = json.loads(pool_path.read_text(encoding="utf-8"))
    assert doc["provider_source"] == "mock_dev_provider"
    assert doc["selected_slate_id"] == "mock-main"


def test_print_pool_report_does_not_crash(tmp_path, capsys):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    print_pool_report(result)
    captured = capsys.readouterr()
    assert "Matched to MLB" in captured.out
    assert "Roster feasibility" in captured.out


def test_build_pool_reports_identity_integrity_summary(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    integrity = result.report["identity_integrity"]
    assert integrity["total"] == 2
    assert integrity["invalid"] == 0
    assert integrity["invalid_rows"] == []
    assert len(result.integrity_results) == 2


def test_provider_players_to_dk_rows_conversion():
    provider_players = [
        {"external_player_id": "mock-1", "name": "X", "team": "AAA", "salary": 5000,
         "position_eligibility": ["1B", "OF"], "game": "AAA@BBB 7:05PM ET"},
    ]
    rows = provider_players_to_dk_rows(provider_players)
    assert len(rows) == 1
    row = rows[0]
    assert row.dk_player_id == "mock-1"
    assert row.team_abbrev == "AAA"
    assert row.dk_positions == ["1B", "OF"]
    assert row.salary == 5000
    assert row.game_info == "AAA@BBB 7:05PM ET"
    assert row.avg_points_per_game is None  # never invented


def test_provider_players_to_dk_rows_handles_missing_optional_fields():
    rows = provider_players_to_dk_rows([{"external_player_id": "mock-1", "name": "X", "team": "AAA", "salary": 5000}])
    assert rows[0].dk_positions == []
    assert rows[0].game_info == ""
