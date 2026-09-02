from dfs.lineup_smoke_test import find_lineups, find_one_legal_lineup
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


def _redundant_pool():
    """A pool with real redundancy at every position, so more than one
    distinct legal lineup genuinely exists -- needed for M6L's
    multiple-lineups/uniqueness tests."""
    pool = [_pitcher(f"p{i}", 3000 + i * 100, "g1") for i in range(4)]
    for slot, prefix in [("C", "c"), ("1B", "1b"), ("2B", "2b"), ("3B", "3b"), ("SS", "ss")]:
        pool.extend(_hitter(f"{prefix}{i}", [slot], 2000 + i * 100, "g1") for i in range(3))
    pool.extend(_hitter(f"of{i}", ["OF"], 2000 + i * 100, "g2") for i in range(6))
    return pool


class TestM6LLocksAndExcludes:
    def test_a_locked_player_always_appears_in_the_returned_lineup(self):
        pool = _cheap_legal_pool()
        lineup = find_one_legal_lineup(pool, salary_cap=50000, locked_player_ids={"c1"})
        assert lineup is not None
        assert "c1" in {p.dk_player_id for p in lineup}
        assert len(lineup) == 10
        assert len({p.dk_player_id for p in lineup}) == 10

    def test_an_excluded_player_never_appears_even_if_otherwise_optimal(self):
        pool = _redundant_pool()  # real redundancy, so a legal lineup still exists after excluding one player
        lineup = find_one_legal_lineup(pool, salary_cap=50000, excluded_player_ids={"c0"})
        assert lineup is not None
        assert "c0" not in {p.dk_player_id for p in lineup}

    def test_locking_a_player_with_no_open_eligible_slot_returns_none_never_drops_the_lock(self):
        pool = _cheap_legal_pool()
        # Two catchers locked -- only one C slot exists, and neither is
        # multi-position -- must fail honestly, never silently drop one.
        pool.append(_hitter("c2", ["C"], 2000, "g1"))
        assert find_one_legal_lineup(pool, salary_cap=50000, locked_player_ids={"c1", "c2"}) is None

    def test_locks_still_respect_the_salary_cap(self):
        pool = _cheap_legal_pool()
        lineup = find_one_legal_lineup(pool, salary_cap=50000, locked_player_ids={"c1"})
        assert lineup is not None
        assert sum(p.salary for p in lineup) <= 50000

    def test_excluding_a_locked_player_id_is_a_contradiction_returns_none(self):
        pool = _cheap_legal_pool()
        assert find_one_legal_lineup(pool, salary_cap=50000, locked_player_ids={"c1"}, excluded_player_ids={"c1"}) is None


class TestM6LFindLineups:
    def test_returns_the_requested_count_of_distinct_legal_lineups(self):
        pool = _redundant_pool()
        lineups = find_lineups(pool, count=3, salary_cap=50000)
        assert len(lineups) == 3
        for lineup in lineups:
            assert len(lineup) == 10
            assert len({p.dk_player_id for p in lineup}) == 10
            assert sum(p.salary for p in lineup) <= 50000

    def test_every_returned_lineup_is_unique(self):
        pool = _redundant_pool()
        lineups = find_lineups(pool, count=4, salary_cap=50000)
        ids = [frozenset(p.dk_player_id for p in lineup) for lineup in lineups]
        assert len(ids) == len(set(ids))

    def test_stops_early_rather_than_fabricating_a_duplicate_when_the_pool_is_exhausted(self):
        pool = _cheap_legal_pool()  # exactly one legal lineup's worth of real redundancy
        lineups = find_lineups(pool, count=5, salary_cap=50000)
        assert len(lineups) <= 1
        assert len(lineups) == len({frozenset(p.dk_player_id for p in lu) for lu in lineups})

    def test_locks_are_honored_across_every_returned_lineup(self):
        pool = _redundant_pool()
        lineups = find_lineups(pool, count=3, salary_cap=50000, locked_player_ids={"p0"})
        assert len(lineups) > 0
        for lineup in lineups:
            assert "p0" in {p.dk_player_id for p in lineup}

    def test_excludes_are_honored_across_every_returned_lineup(self):
        pool = _redundant_pool()
        lineups = find_lineups(pool, count=3, salary_cap=50000, excluded_player_ids={"p0"})
        assert len(lineups) > 0
        for lineup in lineups:
            assert "p0" not in {p.dk_player_id for p in lineup}
