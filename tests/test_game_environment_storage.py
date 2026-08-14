import pytest

from research.game_environment.storage import (
    list_environment_reports,
    load_environment_report,
    load_latest_environment_report,
    save_environment_report,
)


def _doc(date="2026-08-13", generated_at="2026-08-13T18:00:00+00:00"):
    return {"slate_date": date, "generated_at": generated_at, "games": []}


def test_save_creates_expected_path(tmp_path):
    path = save_environment_report(_doc(), output_root=tmp_path)
    assert path.name == "environment_20260813T180000.json"
    assert path.exists()
    assert load_environment_report(path)["slate_date"] == "2026-08-13"


def test_save_never_overwrites(tmp_path):
    save_environment_report(_doc(), output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_environment_report(_doc(), output_root=tmp_path)


def test_load_latest_picks_the_newest(tmp_path):
    save_environment_report(_doc(generated_at="2026-08-13T18:00:00+00:00"), output_root=tmp_path)
    save_environment_report(_doc(generated_at="2026-08-13T19:00:00+00:00"), output_root=tmp_path)
    latest = load_latest_environment_report("2026-08-13", output_root=tmp_path)
    assert latest["generated_at"] == "2026-08-13T19:00:00+00:00"


def test_load_latest_returns_none_when_missing(tmp_path):
    assert load_latest_environment_report("2026-08-13", output_root=tmp_path) is None


def test_list_reports_empty_when_no_folder(tmp_path):
    assert list_environment_reports("2026-08-13", output_root=tmp_path) == []
