import pytest

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.csv_import_pool_provider import CsvImportPoolProvider
from external_projections.persistence import save_baseline_snapshot


def _csv_import_document(**overrides) -> dict:
    doc = {
        "slate_date": "2026-08-14",
        "provider": "bluecollar",
        "provider_name": "BlueCollar DFS",
        "retrieved_at": "2026-08-14T18:00:00+00:00",
        "source": "csv_import",
        "player_count": 2,
        "players": [
            {"external_player_id": "e1", "name": "Ace Pitcher", "team": "TOR", "opponent": "BOS", "position": "P",
             "salary": 9500, "projection": 22.1},
            {"external_player_id": "e2", "name": "Lead Off", "team": "BOS", "opponent": "TOR", "position": "OF",
             "salary": 4200, "projection": 9.4},
        ],
    }
    doc.update(overrides)
    return doc


def test_raises_unavailable_when_no_baseline_exists(tmp_path):
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-14")


def test_raises_unavailable_when_latest_baseline_is_not_csv_import(tmp_path):
    """A MOCK EXTERNAL PROJECTIONS (or any other) baseline must never be
    used as a real salary source here."""
    save_baseline_snapshot(_csv_import_document(source="provider_fetch"), output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-14")


def test_builds_a_pool_from_a_csv_imported_baseline(tmp_path):
    save_baseline_snapshot(_csv_import_document(), output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    result = provider.get_slate("2026-08-14")

    assert len(result.slates) == 1
    players = {p.name: p for p in result.players_by_slate[result.slates[0].slate_id]}
    assert players["Ace Pitcher"].salary == 9500
    assert players["Ace Pitcher"].team == "TOR"
    assert players["Ace Pitcher"].position_eligibility == ["P"]
    assert players["Ace Pitcher"].source == "csv_import_pool"
    assert result.source == "csv_import_pool"


def test_players_missing_salary_team_or_position_are_skipped_not_invented(tmp_path):
    doc = _csv_import_document(players=[
        {"external_player_id": "e1", "name": "Ace Pitcher", "team": "TOR", "opponent": "BOS", "position": "P", "salary": 9500},
        {"external_player_id": "e2", "name": "No Salary Guy", "team": "BOS", "opponent": "TOR", "position": "OF", "salary": None},
    ])
    save_baseline_snapshot(doc, output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    result = provider.get_slate("2026-08-14")
    players = result.players_by_slate[result.slates[0].slate_id]
    assert {p.name for p in players} == {"Ace Pitcher"}
    assert any("skipped" in w.lower() for w in result.warnings)


def test_raises_unavailable_when_zero_players_are_usable(tmp_path):
    doc = _csv_import_document(players=[
        {"external_player_id": "e1", "name": "No Salary Guy", "team": "BOS", "opponent": "TOR", "position": "OF", "salary": None},
    ])
    save_baseline_snapshot(doc, output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-14")


def test_warns_it_is_not_official_draftkings_data(tmp_path):
    save_baseline_snapshot(_csv_import_document(), output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    result = provider.get_slate("2026-08-14")
    assert any("not official DraftKings data" in w for w in result.warnings)


def test_rejects_non_mlb_sport(tmp_path):
    save_baseline_snapshot(_csv_import_document(), output_root=tmp_path)
    provider = CsvImportPoolProvider(external_snapshot_root=tmp_path)
    with pytest.raises(ProviderNoSlateError):
        provider.get_slate("2026-08-14", sport="NFL")


def test_implements_interface():
    assert isinstance(CsvImportPoolProvider(), DFSSalaryProvider)
