import json

import pytest

from config.ownership_config import OWNERSHIP_MODEL_VERSION
from ownership.model import build_ownership_projections
from ownership.persistence import (
    build_ownership_document,
    list_ownership_snapshots,
    load_latest_ownership_snapshot,
    save_ownership_document,
)
from tests._ownership_fixtures import small_slate_hitters, small_slate_pitchers


def _document(generated_at="2026-08-11T18:00:00+00:00"):
    projections, team_pop, report = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    return build_ownership_document(
        "2026-08-11", generated_at, OWNERSHIP_MODEL_VERSION, "dfs_input/2026-08-11/dk_player_pool_x.json",
        "predictions/2026-08-11/pitcher_board_x.json", "predictions/2026-08-11/batter_board_x.json",
        projections, team_pop, report,
    )


def test_document_has_required_provenance_fields():
    doc = _document()
    for field in [
        "slate_date", "generated_at_utc", "generated_at_local", "timezone", "model_version",
        "source_dk_player_pool_path", "pitcher_snapshot_reference", "batter_snapshot_reference",
        "players", "team_popularity", "normalization_checks",
    ]:
        assert field in doc, f"missing field: {field}"
    assert doc["model_version"] == OWNERSHIP_MODEL_VERSION
    assert doc["timezone"] == "America/Chicago"


def test_players_carry_dk_and_mlb_ids_for_future_join():
    doc = _document()
    for p in doc["players"]:
        assert "dk_player_id" in p
        assert "mlb_player_id" in p


def test_save_and_no_overwrite(tmp_path):
    doc = _document()
    path = save_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "ownership_20260811T180000.json"

    with pytest.raises(FileExistsError):
        save_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)


def test_list_and_load_latest_snapshot(tmp_path):
    doc1 = _document(generated_at="2026-08-11T14:00:00+00:00")
    doc2 = _document(generated_at="2026-08-11T20:00:00+00:00")
    save_ownership_document(doc1, "2026-08-11", "20260811T140000", output_root=tmp_path)
    save_ownership_document(doc2, "2026-08-11", "20260811T200000", output_root=tmp_path)

    snapshots = list_ownership_snapshots("2026-08-11", output_root=tmp_path)
    assert len(snapshots) == 2

    latest = load_latest_ownership_snapshot("2026-08-11", output_root=tmp_path)
    assert latest["generated_at_utc"] == "2026-08-11T20:00:00+00:00"


def test_load_latest_raises_when_none_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest_ownership_snapshot("2026-08-11", output_root=tmp_path)


def test_saved_json_round_trips():
    doc = _document()
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        path = save_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=Path(tmp))
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["player_count"] == doc["player_count"]
        assert len(loaded["players"]) == len(doc["players"])
