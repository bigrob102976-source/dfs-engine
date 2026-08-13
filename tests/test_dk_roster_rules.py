from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_CLASSIC_SALARY_CAP, DK_MIN_GAMES_REPRESENTED, DK_ROSTER_SIZE
from dfs.models import DFSPlayer
from dfs.roster_feasibility import check_roster_feasibility


def test_roster_slot_counts_sum_to_ten():
    assert DK_ROSTER_SIZE == 10
    assert sum(s["count"] for s in DK_CLASSIC_ROSTER_SLOTS) == 10


def test_salary_cap_is_fifty_thousand():
    assert DK_CLASSIC_SALARY_CAP == 50000


def test_expected_slot_shape():
    slots = {s["slot"]: s["count"] for s in DK_CLASSIC_ROSTER_SLOTS}
    assert slots == {"P": 2, "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3}


def _hitter(pid, positions, game_id="g1", salary=3000):
    return DFSPlayer(dk_player_id=pid, name=f"H{pid}", team="AAA", player_type="hitter",
                      dk_positions=positions, salary=salary, game_id=game_id, lineup_status="active")


def _pitcher(pid, game_id="g1", salary=8000):
    return DFSPlayer(dk_player_id=pid, name=f"P{pid}", team="AAA", player_type="pitcher",
                      dk_positions=["P"], salary=salary, game_id=game_id, lineup_status="active")


def _full_legal_pool(games=("g1", "g2")):
    pool = [_pitcher("p1", game_id=games[0]), _pitcher("p2", game_id=games[-1])]
    pool.append(_hitter("c1", ["C"], game_id=games[0]))
    pool.append(_hitter("1b1", ["1B"], game_id=games[0]))
    pool.append(_hitter("2b1", ["2B"], game_id=games[0]))
    pool.append(_hitter("3b1", ["3B"], game_id=games[0]))
    pool.append(_hitter("ss1", ["SS"], game_id=games[0]))
    pool.extend([_hitter(f"of{i}", ["OF"], game_id=games[-1]) for i in range(3)])
    return pool


def test_feasibility_passes_with_full_coverage():
    result = check_roster_feasibility(_full_legal_pool())
    assert result.passed is True
    assert result.reasons == []
    assert result.position_counts["OF"] == 3
    assert result.pitcher_count == 2


def test_feasibility_fails_missing_catcher():
    pool = [p for p in _full_legal_pool() if p.dk_player_id != "c1"]
    result = check_roster_feasibility(pool)
    assert result.passed is False
    assert any("C" in r for r in result.reasons)


def test_feasibility_fails_not_enough_outfielders():
    pool = [p for p in _full_legal_pool() if not (p.player_type == "hitter" and "OF" in p.dk_positions)]
    pool.append(_hitter("of1", ["OF"], game_id="g2"))  # only 1 OF now
    result = check_roster_feasibility(pool)
    assert result.passed is False


def test_feasibility_fails_not_enough_pitchers():
    pool = [p for p in _full_legal_pool() if p.player_type != "pitcher"]
    pool.append(_pitcher("p1"))
    result = check_roster_feasibility(pool)
    assert result.passed is False
    assert any("pitcher" in r.lower() for r in result.reasons)


def test_feasibility_fails_when_all_players_from_one_game():
    pool = _full_legal_pool(games=("g1", "g1"))
    result = check_roster_feasibility(pool)
    assert result.passed is False
    assert result.games_represented == 1
    assert any(str(DK_MIN_GAMES_REPRESENTED) in r for r in result.reasons)


def test_multi_position_eligible_hitter_counts_toward_each_slot():
    pool = _full_legal_pool()
    pool.append(_hitter("mp1", ["1B", "OF"], game_id="g1"))
    result = check_roster_feasibility(pool)
    assert result.position_counts["1B"] >= 2
    assert result.position_counts["OF"] >= 4
