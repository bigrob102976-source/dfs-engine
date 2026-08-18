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


def _document(generated_at="2026-08-11T18:00:00+00:00", slate_id=None):
    projections, team_pop, report = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    return build_ownership_document(
        "2026-08-11", generated_at, OWNERSHIP_MODEL_VERSION, "dfs_input/2026-08-11/dk_player_pool_x.json",
        "predictions/2026-08-11/pitcher_board_x.json", "predictions/2026-08-11/batter_board_x.json",
        projections, team_pop, report, slate_id=slate_id,
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


# ----------------------------------------------------------------------------
# Milestone 26: slate-scoped ownership persistence
# ----------------------------------------------------------------------------


def test_document_carries_slate_id_when_provided():
    doc = _document(slate_id="dkcsv-main-2026-08-11")
    assert doc["slate_id"] == "dkcsv-main-2026-08-11"


def test_document_slate_id_defaults_to_none_for_backward_compatibility():
    doc = _document()
    assert doc["slate_id"] is None


def test_slate_scoped_save_path_includes_slate_id(tmp_path):
    doc = _document(slate_id="dkcsv-main-2026-08-11")
    path = save_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path, slate_id="dkcsv-main-2026-08-11")
    assert path == tmp_path / "2026-08-11" / "dkcsv-main-2026-08-11" / "ownership_20260811T180000.json"


def test_omitting_slate_id_preserves_exact_legacy_date_only_path(tmp_path):
    doc = _document()
    path = save_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert path == tmp_path / "2026-08-11" / "ownership_20260811T180000.json"


def test_two_slates_sharing_a_date_never_collide_or_leak(tmp_path):
    # Confirmed real bug this fixes: before Milestone 26, Main and Turbo
    # ownership for the same date both landed in ownership_predictions/
    # <date>/ with no slate discriminator, so selecting Turbo after Main
    # silently changed what "latest ownership" meant for the WHOLE date.
    main_doc = _document(generated_at="2026-08-11T18:00:00+00:00", slate_id="dkcsv-main-2026-08-11")
    turbo_doc = _document(generated_at="2026-08-11T20:00:00+00:00", slate_id="dkcsv-turbo-2026-08-11")

    save_ownership_document(main_doc, "2026-08-11", "20260811T180000", output_root=tmp_path, slate_id="dkcsv-main-2026-08-11")
    save_ownership_document(turbo_doc, "2026-08-11", "20260811T200000", output_root=tmp_path, slate_id="dkcsv-turbo-2026-08-11")

    latest_main = load_latest_ownership_snapshot("2026-08-11", output_root=tmp_path, slate_id="dkcsv-main-2026-08-11")
    latest_turbo = load_latest_ownership_snapshot("2026-08-11", output_root=tmp_path, slate_id="dkcsv-turbo-2026-08-11")

    # Even though Turbo was generated LATER, Main's own "latest" must
    # still resolve to Main's document, never Turbo's.
    assert latest_main["slate_id"] == "dkcsv-main-2026-08-11"
    assert latest_turbo["slate_id"] == "dkcsv-turbo-2026-08-11"
    assert list_ownership_snapshots("2026-08-11", output_root=tmp_path, slate_id="dkcsv-main-2026-08-11") != \
        list_ownership_snapshots("2026-08-11", output_root=tmp_path, slate_id="dkcsv-turbo-2026-08-11")


def test_load_latest_raises_for_a_slate_id_with_no_snapshots_even_if_the_date_has_others(tmp_path):
    main_doc = _document(slate_id="dkcsv-main-2026-08-11")
    save_ownership_document(main_doc, "2026-08-11", "20260811T180000", output_root=tmp_path, slate_id="dkcsv-main-2026-08-11")
    with pytest.raises(FileNotFoundError):
        load_latest_ownership_snapshot("2026-08-11", output_root=tmp_path, slate_id="dkcsv-turbo-2026-08-11")
