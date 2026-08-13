import pytest

from evaluation.actual_ownership_parser import DKResultsFormatError, compute_file_hash, parse_dk_results_csv


def _write(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


_DIRECT_CSV = (
    "Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS\n"
    "1,1,User1,0,150.0,P A P B C C1 1B D 2B E 3B F SS G OF H OF I OF J,,Player A,P,63.40%,29.6\n"
    "2,2,User2,0,148.0,P A P B C C1 1B D 2B E 3B F SS G OF H OF I OF K,,Player B,P,55.30%,22.1\n"
)

_DERIVED_CSV = (
    "Rank,EntryId,EntryName,TimeRemaining,Points,Lineup\n"
    "1,1,User1,0,150.0,P Alpha One P Beta Two C Gamma Three 1B Delta Four 2B Epsilon Five "
    "3B Zeta Six SS Eta Seven OF Theta Eight OF Iota Nine OF Kappa Ten\n"
    "2,2,User2,0,148.0,P Alpha One P Beta Two C Gamma Three 1B Delta Four 2B Epsilon Five "
    "3B Zeta Six SS Eta Seven OF Theta Eight OF Iota Nine OF Lambda Eleven\n"
)

_NO_OWNERSHIP_CSV = "Rank,EntryId,Points\n1,1,100\n"


def test_direct_format_detected_and_parsed(tmp_path):
    path = _write(tmp_path, "contest-standings-123456789.csv", _DIRECT_CSV)
    raw_rows, meta, fmt, warnings = parse_dk_results_csv(path)
    assert fmt == "direct_ownership_table"
    assert len(raw_rows) == 2
    assert raw_rows[0].name == "Player A"
    assert raw_rows[0].actual_ownership == 63.4
    assert warnings == []


def test_contest_id_extracted_from_filename(tmp_path):
    path = _write(tmp_path, "contest-standings-123456789.csv", _DIRECT_CSV)
    _rows, meta, _fmt, _w = parse_dk_results_csv(path)
    assert meta.contest_id == "123456789"


def test_entries_count_reflects_ownership_row_count(tmp_path):
    path = _write(tmp_path, "contest-standings-1.csv", _DIRECT_CSV)
    _rows, meta, _fmt, _w = parse_dk_results_csv(path)
    assert meta.entries == 2


def test_derived_format_used_when_no_direct_ownership_column(tmp_path):
    path = _write(tmp_path, "contest-standings-2.csv", _DERIVED_CSV)
    raw_rows, meta, fmt, warnings = parse_dk_results_csv(path)
    assert fmt == "derived_from_lineups"
    assert meta.entries == 2
    assert warnings  # documents the derivation
    by_name = {r.name: r.actual_ownership for r in raw_rows}
    assert by_name["Alpha One"] == 100.0  # appears in both entries
    assert by_name["Kappa Ten"] == 50.0   # appears in only 1 of 2 entries


def test_derived_format_ownership_percentages_never_exceed_100(tmp_path):
    path = _write(tmp_path, "contest-standings-3.csv", _DERIVED_CSV)
    raw_rows, _meta, _fmt, _warnings = parse_dk_results_csv(path)
    assert all(0.0 <= r.actual_ownership <= 100.0 for r in raw_rows)


def test_neither_format_raises_clear_error(tmp_path):
    path = _write(tmp_path, "mystery.csv", _NO_OWNERSHIP_CSV)
    with pytest.raises(DKResultsFormatError):
        parse_dk_results_csv(path)


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_dk_results_csv("does/not/exist.csv")


def test_empty_file_raises_format_error(tmp_path):
    path = _write(tmp_path, "empty.csv", "")
    with pytest.raises(DKResultsFormatError):
        parse_dk_results_csv(path)


def test_out_of_range_ownership_row_skipped_not_clamped(tmp_path):
    content = (
        "Rank,EntryId,Lineup,,Player,Roster Position,%Drafted,FPTS\n"
        "1,1,x,,Good Player,P,45.00%,10.0\n"
        "2,2,x,,Bad Player,P,150.00%,10.0\n"
        "3,3,x,,Negative Player,P,-5.00%,10.0\n"
    )
    path = _write(tmp_path, "bad-values.csv", content)
    raw_rows, _meta, _fmt, warnings = parse_dk_results_csv(path)
    names = {r.name for r in raw_rows}
    assert "Good Player" in names
    assert "Bad Player" not in names
    assert "Negative Player" not in names
    assert len(warnings) == 2


def test_unparseable_ownership_value_skipped_with_warning(tmp_path):
    content = "Rank,EntryId,Lineup,,Player,Roster Position,%Drafted,FPTS\n1,1,x,,Weird Player,P,N/A,10.0\n"
    path = _write(tmp_path, "unparseable.csv", content)
    raw_rows, _meta, _fmt, warnings = parse_dk_results_csv(path)
    assert raw_rows == []
    assert len(warnings) == 1


def test_file_hash_is_deterministic_and_changes_with_content(tmp_path):
    path1 = _write(tmp_path, "a.csv", _DIRECT_CSV)
    path2 = _write(tmp_path, "b.csv", _DIRECT_CSV)
    path3 = _write(tmp_path, "c.csv", _DIRECT_CSV + "\nextra\n")
    assert compute_file_hash(path1) == compute_file_hash(path2)
    assert compute_file_hash(path1) != compute_file_hash(path3)


def test_percentage_convention_is_points_not_fraction(tmp_path):
    # 63.40% in the CSV must become 63.4, never 0.634.
    path = _write(tmp_path, "pct.csv", _DIRECT_CSV)
    raw_rows, _meta, _fmt, _w = parse_dk_results_csv(path)
    assert raw_rows[0].actual_ownership > 1.0
