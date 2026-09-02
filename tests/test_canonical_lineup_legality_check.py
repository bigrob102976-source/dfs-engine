"""M6L -- scripts/canonical_lineup_legality_check.py: the honest,
non-projection structural bridge proving a canonical player list can
produce real, legal DK Classic MLB lineups (roster rules + salary cap +
locks/excludes/uniqueness), reusing dfs/lineup_smoke_test.py::
find_lineups() unchanged."""

import scripts.canonical_lineup_legality_check as bridge


def _player(provider_player_id, positions, salary, name=None, team="AAA"):
    return {"providerPlayerId": provider_player_id, "name": name or f"Player {provider_player_id}", "team": team, "positions": positions, "salary": salary}


def _redundant_players():
    players = [_player(f"p{i}", ["P"], 3000 + i * 100) for i in range(4)]
    for slot, prefix in [("C", "c"), ("1B", "1b"), ("2B", "2b"), ("3B", "3b"), ("SS", "ss")]:
        players += [_player(f"{prefix}{i}", [slot], 2000 + i * 100) for i in range(3)]
    players += [_player(f"of{i}", ["OF"], 2000 + i * 100) for i in range(6)]
    return players


def test_produces_a_real_legal_lineup_respecting_salary_cap_and_roster_rules():
    payload = {"count": 1, "salaryCap": 50000, "players": _redundant_players()}
    result = bridge.check_for_payload(payload)
    assert result["status"] == "OK"
    assert result["lineupsProduced"] == 1
    lineup = result["lineups"][0]
    assert len(lineup) == 10
    assert len({p["providerPlayerId"] for p in lineup}) == 10
    assert sum(p["salary"] for p in lineup) <= 50000


def test_honors_locks_and_excludes():
    payload = {"count": 1, "salaryCap": 50000, "locks": ["p0"], "excludes": ["c0"], "players": _redundant_players()}
    result = bridge.check_for_payload(payload)
    ids = {p["providerPlayerId"] for p in result["lineups"][0]}
    assert "p0" in ids
    assert "c0" not in ids


def test_multiple_lineups_are_distinct():
    payload = {"count": 3, "salaryCap": 50000, "players": _redundant_players()}
    result = bridge.check_for_payload(payload)
    assert result["lineupsProduced"] == 3
    id_sets = [frozenset(p["providerPlayerId"] for p in lu) for lu in result["lineups"]]
    assert len(id_sets) == len(set(id_sets))


def test_infeasible_pool_produces_zero_lineups_never_a_fake_one():
    payload = {"count": 1, "salaryCap": 50000, "players": [_player("1", ["P"], 3000)]}  # nowhere near a legal roster
    result = bridge.check_for_payload(payload)
    assert result["status"] == "OK"
    assert result["lineupsProduced"] == 0
    assert result["lineups"] == []
