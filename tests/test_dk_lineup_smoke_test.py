from dfs.lineup_smoke_test import find_one_legal_lineup
from dfs.models import DFSPlayer


def _hitter(pid, positions, salary, game_id="g1"):
    return DFSPlayer(dk_player_id=pid, name=f"H{pid}", team="AAA", player_type="hitter",
                      dk_positions=positions, salary=salary, game_id=game_id, lineup_status="active")


def _pitcher(pid, salary, game_id="g1"):
    return DFSPlayer(dk_player_id=pid, name=f"P{pid}", team="AAA", player_type="pitcher",
                      dk_positions=["P"], salary=salary, game_id=game_id, lineup_status="active")


def _cheap_legal_pool():
    pool = [_pitcher("p1", 3000, "g1"), _pitcher("p2", 3000, "g2")]
    pool.append(_hitter("c1", ["C"], 2000, "g1"))
    pool.append(_hitter("1b1", ["1B"], 2000, "g1"))
    pool.append(_hitter("2b1", ["2B"], 2000, "g1"))
    pool.append(_hitter("3b1", ["3B"], 2000, "g1"))
    pool.append(_hitter("ss1", ["SS"], 2000, "g1"))
    pool.extend([_hitter(f"of{i}", ["OF"], 2000, "g2") for i in range(3)])
    return pool


def test_finds_a_legal_lineup_when_one_exists():
    pool = _cheap_legal_pool()
    lineup = find_one_legal_lineup(pool, salary_cap=50000)
    assert lineup is not None
    assert len(lineup) == 10
    assert len({p.dk_player_id for p in lineup}) == 10
    assert sum(p.salary for p in lineup) <= 50000


def test_returns_none_when_a_required_position_is_missing():
    pool = [p for p in _cheap_legal_pool() if p.dk_player_id != "c1"]
    assert find_one_legal_lineup(pool, salary_cap=50000) is None


def test_returns_none_when_salary_cap_cannot_be_met():
    pool = _cheap_legal_pool()
    # Every player costs more than the (absurdly low) cap can ever fit.
    assert find_one_legal_lineup(pool, salary_cap=100) is None


def test_multi_position_player_can_fill_either_slot():
    pool = [p for p in _cheap_legal_pool() if p.dk_player_id != "3b1"]
    pool.append(_hitter("mp1", ["3B", "OF"], 2000, "g1"))
    lineup = find_one_legal_lineup(pool, salary_cap=50000)
    assert lineup is not None


def test_deterministic_across_repeated_calls():
    pool = _cheap_legal_pool()
    first = find_one_legal_lineup(pool, salary_cap=50000)
    second = find_one_legal_lineup(pool, salary_cap=50000)
    assert [p.dk_player_id for p in first] == [p.dk_player_id for p in second]
