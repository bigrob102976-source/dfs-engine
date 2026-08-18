import pytest

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv

_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"


def _write_csv(tmp_path, body: str, header: str = _HEADER):
    path = tmp_path / "DKSalaries.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_parses_basic_row(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        'OF,"Aaron Judge (12345678)",Aaron Judge,12345678,OF,6800,NYY@BOS 07:05PM ET,NYY,12.34\n',
    )
    rows = parse_salary_csv(csv_path)
    assert len(rows) == 1
    row = rows[0]
    assert row.dk_player_id == "12345678"
    assert row.name == "Aaron Judge"
    assert row.team_abbrev == "NYY"
    assert row.dk_positions == ["OF"]
    assert row.salary == 6800
    assert row.game_info == "NYY@BOS 07:05PM ET"
    assert row.avg_points_per_game == 12.34


def test_multi_position_eligibility_splits_on_slash(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        '1B/3B,"Multi Pos (55555)",Multi Pos,55555,1B/3B,4500,NYY@BOS 07:05PM ET,NYY,8.0\n',
    )
    row = parse_salary_csv(csv_path)[0]
    assert row.dk_positions == ["1B", "3B"]


def test_pitcher_position(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        'P,"Some Arm (99999)",Some Arm,99999,P,9200,NYY@BOS 07:05PM ET,NYY,18.0\n',
    )
    row = parse_salary_csv(csv_path)[0]
    assert row.dk_positions == ["P"]


def test_salary_with_dollar_sign_and_commas(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        'OF,"X Y (1)",X Y,1,OF,"$6,800",NYY@BOS 07:05PM ET,NYY,10.0\n',
    )
    row = parse_salary_csv(csv_path)[0]
    assert row.salary == 6800


def test_id_falls_back_to_name_plus_id_column_when_id_column_blank(tmp_path):
    header = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"
    body = 'OF,"Y Z (778899)",Y Z,,OF,4000,NYY@BOS 07:05PM ET,NYY,7.0\n'
    csv_path = _write_csv(tmp_path, body, header)
    row = parse_salary_csv(csv_path)[0]
    assert row.dk_player_id == "778899"


def test_missing_position_column_falls_back_to_roster_position(tmp_path):
    header = "Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"
    body = '"X Y (1)",X Y,1,C,3800,NYY@BOS 07:05PM ET,NYY,6.0\n'
    csv_path = _write_csv(tmp_path, body, header)
    row = parse_salary_csv(csv_path)[0]
    assert row.dk_positions == ["C"]


def test_missing_required_column_raises_format_error(tmp_path):
    header = "Position,Name,ID,Salary,TeamAbbrev,AvgPointsPerGame\n"  # no Game Info
    body = "OF,X Y,1,4000,NYY,6.0\n"
    csv_path = _write_csv(tmp_path, body, header)
    with pytest.raises(DraftKingsCSVFormatError):
        parse_salary_csv(csv_path)


def test_missing_id_columns_entirely_raises_format_error(tmp_path):
    header = "Position,Name,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"  # no ID / Name + ID
    body = "OF,X Y,4000,NYY@BOS 07:05PM ET,NYY,6.0\n"
    csv_path = _write_csv(tmp_path, body, header)
    with pytest.raises(DraftKingsCSVFormatError):
        parse_salary_csv(csv_path)


def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        parse_salary_csv("does/not/exist.csv")


def test_avg_points_per_game_blank_is_none(tmp_path):
    csv_path = _write_csv(tmp_path, 'OF,"X Y (1)",X Y,1,OF,4000,NYY@BOS 07:05PM ET,NYY,\n')
    row = parse_salary_csv(csv_path)[0]
    assert row.avg_points_per_game is None


def test_source_row_number_matches_the_rows_real_line_on_disk(tmp_path):
    # Milestone 27.4 source-to-pool trace: row 1 is the header, so the
    # first data row is disk line 2 -- matches what a human counts when
    # they open the CSV themselves.
    csv_path = _write_csv(
        tmp_path,
        'OF,"First (1)",First,1,OF,4000,NYY@BOS 07:05PM ET,NYY,1.0\n'
        'OF,"Second (2)",Second,2,OF,4000,NYY@BOS 07:05PM ET,NYY,2.0\n'
        'OF,"Third (3)",Third,3,OF,4000,NYY@BOS 07:05PM ET,NYY,3.0\n',
    )
    rows = parse_salary_csv(csv_path)
    assert [r.source_row_number for r in rows] == [2, 3, 4]


def test_source_filename_and_sha256_are_recorded_and_shared_across_rows(tmp_path):
    import hashlib

    csv_path = _write_csv(tmp_path, 'OF,"X Y (1)",X Y,1,OF,4000,NYY@BOS 07:05PM ET,NYY,1.0\n')
    rows = parse_salary_csv(csv_path)
    expected_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert rows[0].source_filename == "DKSalaries.csv"
    assert rows[0].source_sha256 == expected_hash
