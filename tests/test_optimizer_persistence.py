import csv
import json

import pytest

from config.optimizer_config import OPTIMIZER_VERSION
from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from optimizer.persistence import build_lineup_set_document, save_lineup_set_csv, save_lineup_set_json
from tests._optimizer_fixtures import feasible_pool


def _document(tmp_generated_at="2026-08-11T18:00:00+00:00"):
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=2, min_unique=1))
    return build_lineup_set_document(
        "2026-08-11", tmp_generated_at, "dfs_input/2026-08-11/dk_player_pool_x.json",
        "predictions/2026-08-11/pitcher_board_x.json", "predictions/2026-08-11/batter_board_x.json",
        OPTIMIZER_VERSION, OptimizerSettings(num_lineups=2).to_dict(), out.result, out.players_by_key,
    )


def test_document_has_required_provenance_fields():
    doc = _document()
    for field in [
        "slate_date", "generated_at_utc", "generated_at_local", "timezone", "optimizer_version",
        "source_player_pool_path", "pitcher_snapshot_reference", "batter_snapshot_reference",
        "settings", "lineups_requested", "lineups_generated", "lineups",
    ]:
        assert field in doc, f"missing field: {field}"
    assert doc["optimizer_version"] == OPTIMIZER_VERSION
    assert doc["timezone"] == "America/Chicago"


def test_json_save_and_no_overwrite(tmp_path):
    doc = _document()
    path = save_lineup_set_json(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "dk_lineups_20260811T180000.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["lineups_generated"] == doc["lineups_generated"]

    with pytest.raises(FileExistsError):
        save_lineup_set_json(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)


def test_csv_save_and_no_overwrite(tmp_path):
    doc = _document()
    path = save_lineup_set_csv(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "dk_lineups_20260811T180000.csv"

    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Lineup", "P1", "P2", "C", "1B", "2B", "3B", "SS", "OF1", "OF2", "OF3", "Salary", "Projection", "Ceiling"]
    assert len(rows) == 1 + doc["lineups_generated"]

    with pytest.raises(FileExistsError):
        save_lineup_set_csv(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)


def test_csv_rows_populated_with_real_names(tmp_path):
    doc = _document()
    path = save_lineup_set_csv(doc, "2026-08-11", "20260811T190000", output_root=tmp_path)
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    first_data_row = rows[1]
    assert first_data_row[1] != ""  # P1
    assert first_data_row[8] != ""  # OF1
    assert int(first_data_row[11]) <= 50000  # Salary


def test_different_timestamps_do_not_collide(tmp_path):
    doc = _document()
    path1 = save_lineup_set_json(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    path2 = save_lineup_set_json(doc, "2026-08-11", "20260811T190000", output_root=tmp_path)
    assert path1 != path2
    assert path1.exists() and path2.exists()
