"""M1J / M1K -- rawHash and normalizedHash tests."""

import pytest

from canonical.hashing import compute_normalized_hash, compute_raw_hash


def test_raw_hash_identical_bytes_same_hash():
    payload = b'{"draftGroupId": 152904, "players": []}'
    assert compute_raw_hash(payload) == compute_raw_hash(payload)


def test_raw_hash_one_byte_change_different_hash():
    a = b'{"draftGroupId": 152904}'
    b = b'{"draftGroupId": 152905}'
    assert compute_raw_hash(a) != compute_raw_hash(b)


def test_raw_hash_is_lowercase_hex_sha256():
    digest = compute_raw_hash(b"hello")
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises if not valid hex


def test_raw_hash_rejects_non_bytes():
    with pytest.raises(TypeError):
        compute_raw_hash("not bytes")


def _slate(**overrides):
    base = {
        "providerSlateId": "152904", "sport": "MLB", "site": "draftkings",
        "gameIds": ["g1", "g2"], "salaryCap": 50000, "rosterTemplate": {"P": 2, "OF": 3},
        "fetchedAt": "2026-08-31T12:00:00Z", "rawHash": "abc123",
    }
    base.update(overrides)
    return base


def _players():
    return [
        {"providerPlayerId": "1", "providerDraftableIds": ["10"], "salary": 5000, "team": "BOS",
         "opponent": "TOR", "gameId": "g1", "positionEligibility": ["OF"], "rosterSlotEligibility": ["OF"]},
        {"providerPlayerId": "2", "providerDraftableIds": ["20", "21"], "salary": 6000, "team": "TOR",
         "opponent": "BOS", "gameId": "g1", "positionEligibility": ["1B", "OF"], "rosterSlotEligibility": ["1B", "OF"]},
    ]


def test_normalized_hash_deterministic_for_same_input():
    slate, players = _slate(), _players()
    assert compute_normalized_hash(slate, players) == compute_normalized_hash(slate, players)


def test_normalized_hash_player_reorder_same_hash():
    slate, players = _slate(), _players()
    reordered = list(reversed(players))
    assert compute_normalized_hash(slate, players) == compute_normalized_hash(slate, reordered)


def test_normalized_hash_map_key_reorder_same_hash():
    slate = _slate()
    reordered_slate = {k: slate[k] for k in reversed(list(slate.keys()))}
    players = _players()
    assert compute_normalized_hash(slate, players) == compute_normalized_hash(reordered_slate, players)


def test_normalized_hash_position_list_reorder_same_hash():
    players_a = _players()
    players_b = _players()
    players_b[1]["positionEligibility"] = ["OF", "1B"]  # same set, different order
    slate = _slate()
    assert compute_normalized_hash(slate, players_a) == compute_normalized_hash(slate, players_b)


def test_normalized_hash_fetched_at_change_same_hash():
    slate_a = _slate(fetchedAt="2026-08-31T12:00:00Z")
    slate_b = _slate(fetchedAt="2026-08-31T18:30:00Z")
    players = _players()
    assert compute_normalized_hash(slate_a, players) == compute_normalized_hash(slate_b, players)


def test_normalized_hash_raw_hash_change_same_hash():
    slate_a = _slate(rawHash="aaa")
    slate_b = _slate(rawHash="bbb")
    players = _players()
    assert compute_normalized_hash(slate_a, players) == compute_normalized_hash(slate_b, players)


def test_normalized_hash_salary_change_different_hash():
    slate = _slate()
    players_a = _players()
    players_b = _players()
    players_b[0]["salary"] = 5100
    assert compute_normalized_hash(slate, players_a) != compute_normalized_hash(slate, players_b)


def test_normalized_hash_player_membership_change_different_hash():
    slate = _slate()
    players_a = _players()
    players_b = _players() + [{
        "providerPlayerId": "3", "providerDraftableIds": ["30"], "salary": 4000, "team": "BOS",
        "opponent": "TOR", "gameId": "g1", "positionEligibility": ["C"], "rosterSlotEligibility": ["C"],
    }]
    assert compute_normalized_hash(slate, players_a) != compute_normalized_hash(slate, players_b)


def test_normalized_hash_eligibility_change_different_hash():
    slate = _slate()
    players_a = _players()
    players_b = _players()
    players_b[1]["positionEligibility"] = ["1B"]  # dropped OF eligibility, not just reordered
    assert compute_normalized_hash(slate, players_a) != compute_normalized_hash(slate, players_b)


def test_normalized_hash_draftgroup_change_different_hash():
    slate_a = _slate(providerSlateId="152904")
    slate_b = _slate(providerSlateId="152905")
    players = _players()
    assert compute_normalized_hash(slate_a, players) != compute_normalized_hash(slate_b, players)


def test_normalized_hash_draftable_id_change_different_hash():
    slate = _slate()
    players_a = _players()
    players_b = _players()
    players_b[1]["providerDraftableIds"] = ["20"]  # lost a real draftableId
    assert compute_normalized_hash(slate, players_a) != compute_normalized_hash(slate, players_b)
