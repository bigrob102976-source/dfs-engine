import pytest

from external_projections.persistence import (
    list_adjusted_snapshots,
    list_baseline_snapshots,
    load_latest_adjusted_snapshot,
    load_latest_baseline_snapshot,
    load_snapshot,
    save_adjusted_snapshot,
    save_baseline_snapshot,
)


def _baseline_doc(date="2026-08-11", provider="mock_external_projections", retrieved_at="2026-08-11T18:00:00+00:00"):
    return {"slate_date": date, "provider": provider, "retrieved_at": retrieved_at, "players": []}


def _adjusted_doc(date="2026-08-11", generated_at="2026-08-11T19:00:00+00:00"):
    return {"slate_date": date, "generated_at": generated_at, "records": []}


def test_save_baseline_snapshot_creates_expected_path(tmp_path):
    path = save_baseline_snapshot(_baseline_doc(), output_root=tmp_path)
    assert path.name == "provider_mock_external_projections_20260811T180000.json"
    assert path.exists()
    assert load_snapshot(path)["slate_date"] == "2026-08-11"


def test_save_baseline_snapshot_never_overwrites(tmp_path):
    save_baseline_snapshot(_baseline_doc(), output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_baseline_snapshot(_baseline_doc(), output_root=tmp_path)


def test_load_latest_baseline_snapshot_picks_newest(tmp_path):
    save_baseline_snapshot(_baseline_doc(retrieved_at="2026-08-11T18:00:00+00:00"), output_root=tmp_path)
    save_baseline_snapshot(_baseline_doc(retrieved_at="2026-08-11T19:00:00+00:00"), output_root=tmp_path)
    latest = load_latest_baseline_snapshot("2026-08-11", output_root=tmp_path)
    assert latest["retrieved_at"] == "2026-08-11T19:00:00+00:00"


def test_load_latest_baseline_snapshot_none_when_missing(tmp_path):
    assert load_latest_baseline_snapshot("2026-08-11", output_root=tmp_path) is None


def test_load_latest_baseline_snapshot_filters_by_provider(tmp_path):
    save_baseline_snapshot(_baseline_doc(provider="mock_external_projections", retrieved_at="2026-08-11T18:00:00+00:00"), output_root=tmp_path)
    save_baseline_snapshot(_baseline_doc(provider="bluecollar", retrieved_at="2026-08-11T19:00:00+00:00"), output_root=tmp_path)
    latest_mock = load_latest_baseline_snapshot("2026-08-11", provider="mock_external_projections", output_root=tmp_path)
    assert latest_mock["provider"] == "mock_external_projections"


def test_list_baseline_snapshots_empty_when_no_folder(tmp_path):
    assert list_baseline_snapshots("2026-08-11", output_root=tmp_path) == []


def test_save_adjusted_snapshot_creates_expected_path(tmp_path):
    path = save_adjusted_snapshot(_adjusted_doc(), output_root=tmp_path)
    assert path.name == "adjusted_20260811T190000.json"
    assert path.exists()


def test_save_adjusted_snapshot_never_overwrites(tmp_path):
    save_adjusted_snapshot(_adjusted_doc(), output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_adjusted_snapshot(_adjusted_doc(), output_root=tmp_path)


def test_load_latest_adjusted_snapshot_picks_newest(tmp_path):
    save_adjusted_snapshot(_adjusted_doc(generated_at="2026-08-11T19:00:00+00:00"), output_root=tmp_path)
    save_adjusted_snapshot(_adjusted_doc(generated_at="2026-08-11T20:00:00+00:00"), output_root=tmp_path)
    latest = load_latest_adjusted_snapshot("2026-08-11", output_root=tmp_path)
    assert latest["generated_at"] == "2026-08-11T20:00:00+00:00"


def test_list_adjusted_snapshots_empty_when_no_folder(tmp_path):
    assert list_adjusted_snapshots("2026-08-11", output_root=tmp_path) == []
