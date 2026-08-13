import pytest

from ownership.slate_normalization import compute_percentiles, compute_ranks, normalize_with_cap


def test_percentiles_best_is_100_worst_is_0():
    pairs = [("a", 10.0), ("b", 20.0), ("c", 5.0)]
    pct = compute_percentiles(pairs)
    assert pct["b"] == 100.0
    assert pct["c"] == 0.0


def test_percentiles_ties_share_average_percentile():
    pairs = [("a", 10.0), ("b", 20.0), ("c", 20.0), ("d", 5.0)]
    pct = compute_percentiles(pairs)
    assert pct["b"] == pct["c"]


def test_percentiles_single_player_is_neutral():
    pct = compute_percentiles([("a", 42.0)])
    assert pct["a"] == 50.0


def test_percentiles_empty_returns_empty():
    assert compute_percentiles([]) == {}


def test_ranks_best_is_rank_1_descending():
    ranks = compute_ranks([("a", 10.0), ("b", 20.0), ("c", 5.0)], descending=True)
    assert ranks["b"] == 1
    assert ranks["a"] == 2
    assert ranks["c"] == 3


def test_ranks_ties_share_rank_and_skip():
    ranks = compute_ranks([("a", 20.0), ("b", 20.0), ("c", 10.0)], descending=True)
    assert ranks["a"] == 1
    assert ranks["b"] == 1
    assert ranks["c"] == 3


def test_normalize_sum_matches_target_when_no_capping_needed():
    raw = {"a": 10.0, "b": 20.0, "c": 30.0}
    norm = normalize_with_cap(raw, target_sum=200.0)
    assert sum(norm.values()) == pytest.approx(200.0)


def test_normalize_no_value_exceeds_cap():
    raw = {"a": 1000.0, "b": 1.0, "c": 1.0, "d": 1.0}
    norm = normalize_with_cap(raw, target_sum=200.0, cap=100.0)
    assert all(v <= 100.0 for v in norm.values())


def test_normalize_redistributes_capped_excess():
    raw = {"a": 1000.0, "b": 10.0, "c": 10.0, "d": 10.0}
    norm = normalize_with_cap(raw, target_sum=200.0, cap=100.0)
    assert norm["a"] == 100.0
    assert sum(norm.values()) == pytest.approx(200.0)
    # remaining 100 split evenly among b/c/d (equal raw scores)
    assert norm["b"] == pytest.approx(norm["c"]) == pytest.approx(norm["d"])


def test_normalize_no_negative_values():
    raw = {"a": 0.0, "b": 0.0, "c": 5.0}
    norm = normalize_with_cap(raw, target_sum=200.0, cap=100.0)
    assert all(v >= 0.0 for v in norm.values())


def test_normalize_all_zero_raw_scores_still_sums_to_target_when_possible():
    raw = {"a": 0.0, "b": 0.0}
    norm = normalize_with_cap(raw, target_sum=200.0, cap=100.0)
    assert norm["a"] == 100.0
    assert norm["b"] == 100.0


def test_normalize_empty_returns_empty():
    assert normalize_with_cap({}, target_sum=200.0) == {}


def test_normalize_large_pool_sums_correctly_800():
    raw = {f"h{i}": 40.0 + i for i in range(40)}
    norm = normalize_with_cap(raw, target_sum=800.0, cap=100.0)
    assert sum(norm.values()) == pytest.approx(800.0)
    assert all(0.0 <= v <= 100.0 for v in norm.values())
