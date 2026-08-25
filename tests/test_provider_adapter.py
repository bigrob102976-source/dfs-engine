"""Optimizer correctness hotfix: dfs/providers/adapter.py::provider_players_to_dk_rows
must produce dk_positions parity with dfs/draftkings_parser.py's real-CSV
path (both split slash-joined compound position strings), not a
provider-shaped raw pass-through.

Reproduced live against a real DRAFTKINGS_UNOFFICIAL_LIVE Featured slate:
dfs_input/<date>/dk_player_pool_*.json had dk_positions == ["3B/OF"] for
multi-position-eligible hitters (18 of 122 optimizer-eligible players,
~15% of the slate's usable hitters) -- optimizer/solver.py::eligible_for_slot()
does an exact-membership check ("3B" in dk_positions) that can never match
a compound string, so every one of those players was silently excluded
from EVERY roster slot. Never surfaced as an error; the optimizer just
quietly solved against a smaller pool than it should have.
"""

from dfs.providers.adapter import provider_players_to_dk_rows


def _player(**overrides):
    base = {"external_player_id": "d1", "name": "Test Player", "team": "BOS", "salary": 4000, "position_eligibility": ["OF"]}
    base.update(overrides)
    return base


def test_single_position_player_is_unaffected():
    rows = provider_players_to_dk_rows([_player(position_eligibility=["OF"])])
    assert rows[0].dk_positions == ["OF"]


def test_compound_slash_joined_position_string_is_split_into_separate_entries():
    rows = provider_players_to_dk_rows([_player(position_eligibility=["3B/OF"])])
    assert rows[0].dk_positions == ["3B", "OF"]


def test_three_way_compound_position_string_splits_correctly():
    rows = provider_players_to_dk_rows([_player(position_eligibility=["1B/3B/OF"])])
    assert rows[0].dk_positions == ["1B", "3B", "OF"]


def test_already_separate_position_entries_are_preserved_and_deduplicated():
    # Some providers may already emit one entry per position (matching
    # DK's own per-draftable-row shape) -- must behave identically to the
    # compound-string case, never double-counting a position seen twice.
    rows = provider_players_to_dk_rows([_player(position_eligibility=["3B", "OF", "OF"])])
    assert rows[0].dk_positions == ["3B", "OF"]


def test_pitcher_position_strings_pass_through_unaffected():
    # Pitcher roster-slot eligibility (optimizer/solver.py::eligible_for_slot)
    # is decided by player_type == "pitcher", never by parsing "SP"/"RP" --
    # this only confirms the split doesn't corrupt a pitcher's raw label.
    rows = provider_players_to_dk_rows([_player(position_eligibility=["SP"])])
    assert rows[0].dk_positions == ["SP"]


def test_missing_or_empty_position_eligibility_stays_empty():
    rows = provider_players_to_dk_rows([_player(position_eligibility=[])])
    assert rows[0].dk_positions == []
    rows2 = provider_players_to_dk_rows([{k: v for k, v in _player().items() if k != "position_eligibility"}])
    assert rows2[0].dk_positions == []


def test_other_dk_salary_row_fields_are_unaffected_by_the_split_fix():
    rows = provider_players_to_dk_rows([_player(external_player_id="d99", name="Zack Gelof", team="OAK", salary=3800, position_eligibility=["3B/OF"], game="OAK@BOS")])
    row = rows[0]
    assert row.dk_player_id == "d99"
    assert row.name == "Zack Gelof"
    assert row.team_abbrev == "OAK"
    assert row.salary == 3800
    assert row.game_info == "OAK@BOS"
    assert row.dk_positions == ["3B", "OF"]
