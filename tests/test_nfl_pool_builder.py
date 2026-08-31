"""NFL M2 -- targeted tests for nfl/pool_builder.py's canonical player
normalization and pool-level validation. All fixtures are synthetic,
mirroring the real payload shape confirmed live against DraftGroup
151307 (NFL M2's own investigation notes): rosterSlotId 66=QB, 67=RB,
68=WR, 69=TE, 70=FLEX (RB/WR/TE only), 71=DST; RB/WR/TE always appear
as two rows (base slot + FLEX), QB/DST as exactly one row each. No
network calls."""

import pytest

from draftkings_unofficial.models import DkDraftable, DkRosterRules, DkRosterSlot, DkSlateGame, DkTeam
from nfl.pool_builder import NflPoolBuildError, _normalize_players, _slot_name_map, validate_pool

DG_ID = 151307
PROVENANCE = "DRAFTKINGS_UNOFFICIAL_LIVE"


def _game(competition_id=100, home="PHI", away="DAL"):
    return DkSlateGame(
        competition_id=competition_id, sport_id=1, name=f"{away} @ {home}", start_time="2026-09-13T17:00:00Z",
        home_team=DkTeam(team_id=1, abbreviation=home), away_team=DkTeam(team_id=2, abbreviation=away),
    )


def _rules():
    names = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    slots = [DkRosterSlot(roster_slot_id=60 + i, name=n) for i, n in enumerate(names)]
    return DkRosterRules(game_type_id=1, sport_id=1, name="Classic", draft_type="SalaryCap", salary_cap_enabled=True, salary_cap=50000, roster_slots=slots)


SLOT_QB, SLOT_RB, SLOT_WR, SLOT_TE, SLOT_FLEX, SLOT_DST = 60, 61, 63, 66, 67, 68


def _draftable(player_id, name, team, position, roster_slot_id, competition_id=100, salary=6000, draftable_id=None, status="None", first_name=None, last_name=None, player_dk_id=None):
    if draftable_id is None:
        draftable_id = (player_id * 10 + roster_slot_id) if player_id is not None else roster_slot_id
    if player_dk_id is None and player_id is not None:
        player_dk_id = player_id * 100
    return DkDraftable(
        draftable_id=draftable_id, draft_group_id=DG_ID,
        player_id=player_id, player_dk_id=player_dk_id,
        display_name=name, first_name=first_name, last_name=last_name,
        position=position, roster_slot_id=roster_slot_id, salary=salary, status=status,
        team_id=1, team_abbreviation=team, competition_id=competition_id,
    )


def _full_slate():
    games = [_game()]
    draftables = [
        _draftable(1, "Starting QB", "PHI", "QB", SLOT_QB, first_name="Starting", last_name="QB", salary=7500),
        _draftable(2, "Starting RB", "DAL", "RB", SLOT_RB, salary=6500),
        _draftable(2, "Starting RB", "DAL", "RB", SLOT_FLEX, draftable_id=2002, salary=6500),
        _draftable(3, "Starting WR", "PHI", "WR", SLOT_WR, salary=5500, status="Q"),
        _draftable(3, "Starting WR", "PHI", "WR", SLOT_FLEX, draftable_id=3002, salary=5500, status="Q"),
        _draftable(4, "Starting TE", "DAL", "TE", SLOT_TE, salary=4500),
        _draftable(4, "Starting TE", "DAL", "TE", SLOT_FLEX, draftable_id=4002, salary=4500),
        _draftable(5, "Eagles", "PHI", "DST", SLOT_DST, salary=2500, first_name="Eagles", last_name=""),
    ]
    return games, draftables


def test_slot_name_map_from_real_roster_rules():
    slot_names = _slot_name_map(_rules())
    assert slot_names[SLOT_QB] == "QB"
    assert slot_names[SLOT_FLEX] == "FLEX"
    assert slot_names[SLOT_DST] == "DST"


def test_normalize_players_full_slate():
    games, draftables = _full_slate()
    slot_names = _slot_name_map(_rules())
    players = _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)

    assert len(players) == 5
    by_id = {p.draftkings_player_id: p for p in players}

    qb = by_id["1"]
    assert qb.position == "QB"
    assert qb.roster_slots == ["QB"]
    assert qb.is_team_entity is False
    assert qb.salary == 7500
    assert qb.injury_status is None  # status "None" -> no injury

    rb = by_id["2"]
    assert rb.position == "RB"
    assert rb.roster_slots == ["RB", "FLEX"]  # FLEX-eligible, never collapsed into position
    assert set(rb.draftable_ids) == {"81", "2002"}  # base slot (2*10+61) + explicit FLEX row

    wr = by_id["3"]
    assert wr.status == "Q"
    assert wr.injury_status == "Q"  # real injury designation preserved, never dropped

    dst = by_id["5"]
    assert dst.position == "DST"
    assert dst.is_team_entity is True
    assert dst.roster_slots == ["DST"]  # DST is never FLEX-eligible

    # Opponent/game resolution from DK's own structured competition data.
    assert qb.team == "PHI"
    assert qb.opponent == "DAL"
    assert rb.team == "DAL"
    assert rb.opponent == "PHI"
    assert qb.game_description == "DAL @ PHI"


def test_flex_never_becomes_a_base_position():
    games, draftables = _full_slate()
    slot_names = _slot_name_map(_rules())
    players = _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)
    assert all(p.position != "FLEX" for p in players)


def test_ambiguous_base_slots_raises():
    """A player with two DIFFERENT non-FLEX base slots (never observed
    live, but structurally invalid) must fail loudly, never guess."""
    games = [_game()]
    draftables = [
        _draftable(1, "Weird Player", "PHI", "RB", SLOT_RB),
        _draftable(1, "Weird Player", "PHI", "WR", SLOT_WR, draftable_id=999),
    ]
    slot_names = _slot_name_map(_rules())
    with pytest.raises(NflPoolBuildError):
        _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)


def test_missing_player_id_raises():
    games = [_game()]
    draftables = [_draftable(None, "No ID Player", "PHI", "QB", SLOT_QB, draftable_id=1)]
    slot_names = _slot_name_map(_rules())
    with pytest.raises(NflPoolBuildError):
        _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)


def test_unknown_competition_raises():
    games = [_game(competition_id=100)]
    draftables = [_draftable(1, "Ghost Player", "PHI", "QB", SLOT_QB, competition_id=999)]
    slot_names = _slot_name_map(_rules())
    with pytest.raises(NflPoolBuildError):
        _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)


def test_validate_pool_passes_on_full_valid_slate():
    games, draftables = _full_slate()
    slot_names = _slot_name_map(_rules())
    players = _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", PROVENANCE)
    result = validate_pool(players, DG_ID)
    assert result.passed is True
    assert result.total_players == 5
    assert result.position_counts == {"QB": 1, "RB": 1, "WR": 1, "TE": 1, "DST": 1}
    assert result.team_count == 2
    assert result.game_count == 1
    assert result.salary_min == 2500
    assert result.salary_max == 7500


def test_validate_pool_blocks_on_empty_pool():
    result = validate_pool([], DG_ID)
    assert result.passed is False
    assert any(f.level == "BLOCK" and "Zero players" in f.message for f in result.findings)


def test_validate_pool_blocks_wrong_provenance():
    games, draftables = _full_slate()
    slot_names = _slot_name_map(_rules())
    players = _normalize_players(draftables, games, slot_names, DG_ID, "2026-09-13", "Featured", "UNOFFICIAL_DEVELOPMENT_SOURCE")
    result = validate_pool(players, DG_ID, expected_provenance=PROVENANCE)
    assert result.passed is False
    assert any(f.level == "BLOCK" and "provenance" in f.message for f in result.findings)
