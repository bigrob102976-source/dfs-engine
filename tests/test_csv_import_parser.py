import pytest

from external_projections.csv_import.parser import CsvParseError, decode_csv_bytes, parse_csv_text


def test_decodes_utf8_sig():
    raw = "Player,Team\nAaron Judge,NYY\n".encode("utf-8-sig")
    text = decode_csv_bytes(raw)
    assert "Aaron Judge" in text


def test_decodes_latin1_fallback_for_unknown_encoding():
    raw = "Player,Team\nJos\xe9 Ram\xedrez,CLE\n".encode("latin-1")
    text = decode_csv_bytes(raw)
    assert "CLE" in text


def test_decode_empty_bytes_returns_empty_string():
    assert decode_csv_bytes(b"") == ""


def test_parse_basic_csv():
    headers, rows, warnings = parse_csv_text("Player,Team,Proj\nAaron Judge,NYY,12.5\n")
    assert headers == ["Player", "Team", "Proj"]
    assert rows == [{"Player": "Aaron Judge", "Team": "NYY", "Proj": "12.5"}]
    assert warnings == []


def test_empty_file_produces_no_rows_and_a_warning():
    headers, rows, warnings = parse_csv_text("")
    assert headers == []
    assert rows == []
    assert "empty" in warnings[0].lower()


def test_header_only_file_produces_no_rows():
    headers, rows, warnings = parse_csv_text("Player,Team\n")
    assert headers == ["Player", "Team"]
    assert rows == []
    assert any("no data rows" in w for w in warnings)


def test_blank_header_row_is_treated_as_no_header():
    headers, rows, warnings = parse_csv_text(",,\n")
    assert headers == []
    assert rows == []
    assert any("no header row" in w for w in warnings)


def test_duplicate_columns_are_renamed_and_warned():
    headers, rows, warnings = parse_csv_text("Player,Team,Team\nAaron Judge,NYY,AL East\n")
    assert headers == ["Player", "Team", "Team (2)"]
    assert rows[0]["Team"] == "NYY"
    assert rows[0]["Team (2)"] == "AL East"
    assert any("Duplicate column" in w for w in warnings)


def test_ragged_rows_are_padded_and_warned():
    headers, rows, warnings = parse_csv_text("Player,Team,Proj\nAaron Judge,NYY\nShohei Ohtani,LAD,15.0,extra\n")
    assert rows[0]["Proj"] == ""  # padded, missing trailing column
    assert rows[1]["Proj"] == "15.0"  # extra trailing column truncated
    assert any("different number of columns" in w for w in warnings)


def test_blank_lines_are_skipped_not_treated_as_data_rows():
    headers, rows, warnings = parse_csv_text("Player,Team\nAaron Judge,NYY\n\n\nShohei Ohtani,LAD\n")
    assert len(rows) == 2


def test_corrupted_csv_never_crashes_the_caller():
    # A pathological but still-decodable string -- parser must return
    # gracefully (empty rows + warnings), never raise for merely "weird" input.
    headers, rows, warnings = parse_csv_text('"unterminated quote,Player,Team\nJudge,NYY\n')
    assert isinstance(headers, list)
    assert isinstance(rows, list)
    assert isinstance(warnings, list)
