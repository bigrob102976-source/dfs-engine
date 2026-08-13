import pytest

from dfs.models import DFSPlayer
from dfs.persistence import save_match_report, save_player_pool, save_raw_csv


def _player(pid="1"):
    return DFSPlayer(dk_player_id=pid, name="X", team="AAA", player_type="hitter",
                      dk_positions=["OF"], salary=4000, lineup_status="active")


def test_raw_csv_copy_is_byte_identical_and_immutable(tmp_path):
    source = tmp_path / "DKSalaries.csv"
    source.write_text("Position,Name\nOF,X\n", encoding="utf-8")
    output_root = tmp_path / "dfs_input"

    dest = save_raw_csv(source, "2026-08-11", "20260811T180000", output_root=output_root)
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert dest.name == "DKSalaries_20260811T180000.csv"

    with pytest.raises(FileExistsError):
        save_raw_csv(source, "2026-08-11", "20260811T180000", output_root=output_root)


def test_player_pool_save_and_no_overwrite(tmp_path):
    output_root = tmp_path / "dfs_input"
    players = [_player("1"), _player("2")]
    path = save_player_pool(players, {"slate_date": "2026-08-11"}, "2026-08-11", "20260811T180000", output_root=output_root)
    assert path.exists()
    assert path.name == "dk_player_pool_20260811T180000.json"

    with pytest.raises(FileExistsError):
        save_player_pool(players, {}, "2026-08-11", "20260811T180000", output_root=output_root)


def test_player_pool_json_preserves_every_player_and_metadata(tmp_path):
    import json
    output_root = tmp_path / "dfs_input"
    players = [_player("1"), _player("2"), _player("3")]
    path = save_player_pool(players, {"slate_date": "2026-08-11", "csv_source": "foo.csv"},
                             "2026-08-11", "20260811T180000", output_root=output_root)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["player_count"] == 3
    assert len(doc["players"]) == 3
    assert doc["csv_source"] == "foo.csv"


def test_match_report_save_and_no_overwrite(tmp_path):
    output_root = tmp_path / "dfs_input"
    report = {"dk_entries": 5}
    path = save_match_report(report, "2026-08-11", "20260811T180000", output_root=output_root)
    assert path.exists()
    assert path.name == "dk_match_report_20260811T180000.json"

    with pytest.raises(FileExistsError):
        save_match_report(report, "2026-08-11", "20260811T180000", output_root=output_root)


def test_different_timestamps_never_collide(tmp_path):
    output_root = tmp_path / "dfs_input"
    report = {"dk_entries": 5}
    path1 = save_match_report(report, "2026-08-11", "20260811T180000", output_root=output_root)
    path2 = save_match_report(report, "2026-08-11", "20260811T190000", output_root=output_root)
    assert path1 != path2
    assert path1.exists() and path2.exists()
