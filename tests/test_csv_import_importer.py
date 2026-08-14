import json

from external_projections.csv_import.importer import analyze_import, build_baseline_document
from external_projections.csv_import.parser import CsvParseError

import pytest


def _write_research_package(root, date):
    folder = root / date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text(json.dumps([
        {"game_id": "111", "home_team_abbr": "BOS", "away_team_abbr": "NYY"},
    ]), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps([
        {"team_id": "1", "abbreviation": "BOS", "name": "Red Sox", "league": "AL", "division": "East"},
        {"team_id": "2", "abbreviation": "NYY", "name": "Yankees", "league": "AL", "division": "East"},
    ]), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps([]), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps([
        {"player_id": "2001", "name": "Aaron Judge", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111", "position": "OF"},
    ]), encoding="utf-8")


_CSV = (
    "Player,Team,Opponent,Position,Salary,Proj,Ceiling,Floor,Own%\n"
    "Aaron Judge,NYY,BOS,OF,6500,12.5,20.0,4.0,24.3\n"
    "Nobody Real,NYY,BOS,OF,5000,8.0,15.0,2.0,10.0\n"
    "Missing Projection Guy,NYY,BOS,OF,4500,,,,\n"
)


def test_analyze_import_happy_path(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    analysis = analyze_import(_CSV.encode("utf-8"), "bluecollar", "2026-08-11", research_output_root=str(tmp_path))
    assert analysis.detected_mapping["name"] == "Player"
    assert analysis.validation.players_imported == 3
    assert analysis.validation.matched == 1
    assert analysis.validation.unmatched == 2
    assert analysis.validation.missing_projection == 1
    assert analysis.importable_player_count == 2  # 3 named rows minus the one missing a projection
    assert len(analysis.preview_rows) == 3


def test_analyze_import_manual_mapping_override(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    csv_text = "Full Name,Squad,Points\nAaron Judge,NYY,12.5\n"
    analysis = analyze_import(
        csv_text.encode("utf-8"), "custom_csv", "2026-08-11",
        manual_mapping={"name": "Full Name", "team": "Squad", "projection": "Points"},
        research_output_root=str(tmp_path),
    )
    assert analysis.resolved_mapping["name"] == "Full Name"
    assert analysis.validation.matched == 1


def test_analyze_import_gracefully_degrades_with_no_research_package(tmp_path):
    # No research package written at all -- matching can't run (and must
    # never attempt to auto-build one over the network, see matcher.py's
    # module docstring), but structural analysis (detection, missing-field
    # counts) must still work.
    analysis = analyze_import(_CSV.encode("utf-8"), "bluecollar", "2099-01-01", research_output_root=str(tmp_path / "nothing_here"))
    assert analysis.validation.players_imported == 3
    assert analysis.validation.matched == 0
    assert analysis.validation.unmatched == 0
    # With no known slate to check against, every team value is honestly
    # "unknown" -- never assumed valid just because matching couldn't run.
    assert analysis.validation.unknown_teams == ["NYY"]


def test_build_baseline_document_shape(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    doc = build_baseline_document(_CSV.encode("utf-8"), "bluecollar", "2026-08-11", "mock.csv", research_output_root=str(tmp_path))
    assert doc["source"] == "csv_import"
    assert doc["provider"] == "bluecollar"
    assert doc["provider_name"] == "BlueCollar DFS"
    assert doc["is_mock"] is False
    assert doc["original_filename"] == "mock.csv"
    # 3 named rows, 1 missing projection -- only 2 make it into the snapshot.
    assert doc["player_count"] == 2
    assert len(doc["players"]) == 2
    names = {p["name"] for p in doc["players"]}
    assert names == {"Aaron Judge", "Nobody Real"}
    assert doc["validation_summary"]["matched"] == 1


def test_build_baseline_document_never_invents_missing_optional_fields(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    csv_text = "Player,Team,Proj\nAaron Judge,NYY,12.5\n"
    doc = build_baseline_document(csv_text.encode("utf-8"), "custom_csv", "2026-08-11", "mock.csv", research_output_root=str(tmp_path))
    player = doc["players"][0]
    assert player["salary"] is None
    assert player["ceiling"] is None
    assert player["floor"] is None
    assert player["ownership_projection"] is None


def test_build_baseline_document_zero_players_when_all_rows_unusable(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    csv_text = "Player,Team,Proj\n,,\n"
    doc = build_baseline_document(csv_text.encode("utf-8"), "custom_csv", "2026-08-11", "mock.csv", research_output_root=str(tmp_path))
    assert doc["player_count"] == 0


def test_undecodable_csv_raises_csv_parse_error(tmp_path):
    # A byte sequence with a leading UTF-16 BOM but otherwise structured
    # as UTF-16 text will not decode cleanly under any of the attempted
    # 8-bit encodings' expectations for this helper to treat as garbage --
    # exercised indirectly by forcing decode_csv_bytes' own contract via analyze_import.
    from external_projections.csv_import import parser as parser_module

    original = parser_module._ENCODINGS_TO_TRY
    try:
        parser_module._ENCODINGS_TO_TRY = ()  # simulate "no usable encoding" without needing exotic bytes
        with pytest.raises(CsvParseError):
            analyze_import(b"Player,Team\nAaron Judge,NYY\n", "custom_csv", "2026-08-11", research_output_root=str(tmp_path))
    finally:
        parser_module._ENCODINGS_TO_TRY = original
