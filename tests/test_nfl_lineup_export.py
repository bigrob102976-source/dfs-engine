"""NFL M14 -- targeted tests for nfl/lineup_export.py: DK-ready CSV
export, including DK's real duplicate-column-name header shape
(RB, RB, WR, WR, WR) which a dict-based CSV reader/writer cannot
represent."""

import pytest

from nfl.lineup_export import (
    DK_NFL_CSV_HEADER,
    LineupExportError,
    export_lineups_to_csv,
    export_saved_lineups_to_csv,
    fill_dk_template_csv,
    fill_dk_template_csv_from_saved,
    format_dk_player_cell,
    lineup_to_dk_row,
    saved_lineup_to_dk_row,
)
from nfl.optimizer_models import NflLineup, NflLineupSlotAssignment, NflOptimizerPlayer
from nfl.saved_lineup_models import NflSavedLineup, NflSavedLineupSlot

DG_ID = 151307
DATE = "2026-09-13"


def _player(key, name, position, salary, team="BUF"):
    return NflOptimizerPlayer(
        key=key, name=name, team=team, opponent="MIA", game_id="100", position=position,
        roster_slots=[position, "FLEX"] if position in ("RB", "WR", "TE") else [position],
        salary=salary, is_team_entity=(position == "DST"), draft_group_id=DG_ID, slate_date=DATE,
    )


def _valid_pool_and_lineup():
    specs = [
        ("QB", "1", "QB One", "QB", 5000), ("RB1", "2", "RB One", "RB", 5000), ("RB2", "3", "RB Two", "RB", 5000),
        ("WR1", "4", "WR One", "WR", 5000), ("WR2", "5", "WR Two", "WR", 5000), ("WR3", "6", "WR Three", "WR", 5000),
        ("TE", "7", "TE One", "TE", 5000), ("FLEX", "8", "FLEX RB", "RB", 5000), ("DST", "9", "Team DST", "DST", 5000),
    ]
    players = {pid: _player(pid, name, pos, sal) for _slot, pid, name, pos, sal in specs}
    assignments = [
        NflLineupSlotAssignment(slot=slot, draftkings_player_id=pid, name=name, position=pos, team="BUF", salary=sal)
        for slot, pid, name, pos, sal in specs
    ]
    total_salary = sum(a.salary for a in assignments)
    lineup = NflLineup(
        index=0, assignments=assignments, total_salary=total_salary, remaining_salary=50000 - total_salary,
        draft_group_id=DG_ID, slate_date=DATE,
    )
    return players, lineup


def test_format_dk_player_cell_real_dk_convention():
    assert format_dk_player_cell("Patrick Mahomes", "39971620") == "Patrick Mahomes (39971620)"


def test_lineup_to_dk_row_correct_slot_order():
    players, lineup = _valid_pool_and_lineup()
    row = lineup_to_dk_row(lineup, players)
    assert row == [
        "QB One (1)", "RB One (2)", "RB Two (3)", "WR One (4)", "WR Two (5)", "WR Three (6)",
        "TE One (7)", "FLEX RB (8)", "Team DST (9)",
    ]


def test_lineup_to_dk_row_uses_dk_id_never_name_alone():
    players, lineup = _valid_pool_and_lineup()
    row = lineup_to_dk_row(lineup, players)
    assert all("(" in cell and cell.endswith(")") for cell in row)


def test_export_invalid_lineup_raises_never_silently_exports():
    players, lineup = _valid_pool_and_lineup()
    lineup.total_salary = 999999  # corrupt: exceeds cap
    with pytest.raises(LineupExportError):
        lineup_to_dk_row(lineup, players)


def test_export_missing_slot_raises():
    players, lineup = _valid_pool_and_lineup()
    lineup.assignments = [a for a in lineup.assignments if a.slot != "DST"]
    lineup.total_salary = sum(a.salary for a in lineup.assignments)
    with pytest.raises((LineupExportError,)):
        lineup_to_dk_row(lineup, players)


def test_export_lineups_to_csv_header_and_row_count():
    players, lineup = _valid_pool_and_lineup()
    csv_text = export_lineups_to_csv([lineup], players)
    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == ",".join(DK_NFL_CSV_HEADER)
    assert len(lines) == 2  # header + 1 lineup row


def test_fill_dk_template_csv_handles_duplicate_rb_wr_columns():
    """The critical regression: DK's real header has RB twice and WR
    three times -- a naive dict-based CSV approach cannot represent
    this at all (duplicate dict keys collide)."""
    template = "Entry ID,Contest Name,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n12345,Main Contest,,,,,,,,,\n"
    players, lineup = _valid_pool_and_lineup()
    filled = fill_dk_template_csv(template, [lineup], players)
    lines = filled.strip("\n").split("\n")
    assert lines[0] == "Entry ID,Contest Name,QB,RB,RB,WR,WR,WR,TE,FLEX,DST"
    data_cells = lines[1].split(",")
    assert data_cells[0] == "12345"  # Entry ID preserved verbatim
    assert data_cells[1] == "Contest Name" or data_cells[1] == "Main Contest"
    assert data_cells[2] == "QB One (1)"
    assert data_cells[3] == "RB One (2)"
    assert data_cells[4] == "RB Two (3)"  # the SECOND "RB" column gets the SECOND RB, not a duplicate of the first
    assert data_cells[5] == "WR One (4)"
    assert data_cells[6] == "WR Two (5)"
    assert data_cells[7] == "WR Three (6)"


def test_fill_dk_template_csv_missing_column_raises():
    template = "Entry ID,QB,RB,WR,WR,WR,TE,FLEX,DST\n1,,,,,,,,,\n"  # only one RB column -- real DK needs two
    players, lineup = _valid_pool_and_lineup()
    with pytest.raises(LineupExportError):
        fill_dk_template_csv(template, [lineup], players)


def test_fill_dk_template_csv_too_few_rows_raises():
    template = "Entry ID,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n"  # header only, no data rows
    players, lineup = _valid_pool_and_lineup()
    with pytest.raises(LineupExportError):
        fill_dk_template_csv(template, [lineup], players)


def test_fill_dk_template_csv_never_touches_non_roster_columns():
    template = "Entry ID,Contest Name,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n999,My Real Contest,,,,,,,,,\n"
    players, lineup = _valid_pool_and_lineup()
    filled = fill_dk_template_csv(template, [lineup], players)
    assert "999" in filled
    assert "My Real Contest" in filled


# ---------------------------------------------------------------------------
# NFL M14 -- saved-lineup export (no live pool needed)
# ---------------------------------------------------------------------------

def _saved_lineup():
    specs = [
        ("QB", "1", "QB One", "QB", 5000), ("RB1", "2", "RB One", "RB", 5000), ("RB2", "3", "RB Two", "RB", 5000),
        ("WR1", "4", "WR One", "WR", 5000), ("WR2", "5", "WR Two", "WR", 5000), ("WR3", "6", "WR Three", "WR", 5000),
        ("TE", "7", "TE One", "TE", 5000), ("FLEX", "8", "FLEX RB", "RB", 5000), ("DST", "9", "Team DST", "DST", 5000),
    ]
    slots = [
        NflSavedLineupSlot(
            roster_slot=slot, draftkings_player_id=pid, name=name, team="BUF", opponent="MIA", game_id="100",
            game_start_utc="2026-09-13T17:00:00+00:00", position=pos, salary=sal,
        )
        for slot, pid, name, pos, sal in specs
    ]
    return NflSavedLineup(
        lineup_id="l1", sport="NFL", site="DraftKings", draft_group_id=DG_ID, slate_date=DATE,
        created_at="2026-09-10T00:00:00+00:00", updated_at="2026-09-10T00:00:00+00:00",
        mode="projection", stack_config={}, slots=slots,
    )


def test_saved_lineup_to_dk_row_matches_live_lineup_row_shape():
    saved = _saved_lineup()
    row = saved_lineup_to_dk_row(saved)
    assert row == [
        "QB One (1)", "RB One (2)", "RB Two (3)", "WR One (4)", "WR Two (5)", "WR Three (6)",
        "TE One (7)", "FLEX RB (8)", "Team DST (9)",
    ]


def test_saved_lineup_export_rejects_duplicate_player_corruption():
    saved = _saved_lineup()
    saved.slots[1].draftkings_player_id = saved.slots[0].draftkings_player_id
    with pytest.raises(Exception):
        saved_lineup_to_dk_row(saved)


def test_export_saved_lineups_to_csv():
    csv_text = export_saved_lineups_to_csv([_saved_lineup()])
    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == ",".join(DK_NFL_CSV_HEADER)
    assert len(lines) == 2


def test_fill_dk_template_csv_from_saved_handles_duplicate_columns():
    template = "Entry ID,Contest Name,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n555,My Contest,,,,,,,,,\n"
    filled = fill_dk_template_csv_from_saved(template, [_saved_lineup()])
    data_cells = filled.strip("\n").split("\n")[1].split(",")
    assert data_cells[0] == "555"
    assert data_cells[3] == "RB One (2)"
    assert data_cells[4] == "RB Two (3)"
