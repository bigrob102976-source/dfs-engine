from evaluation.projection_source_comparison import (
    compare_projection_sources,
    evaluate_projection_source,
)


def test_perfect_predictions_give_zero_error_and_full_correlation():
    predicted = {"a": 10.0, "b": 20.0, "c": 30.0}
    actual = {"a": 10.0, "b": 20.0, "c": 30.0}
    metrics = evaluate_projection_source("independent", predicted, actual)
    assert metrics.n == 3
    assert metrics.mae == 0.0
    assert metrics.rmse == 0.0
    assert metrics.correlation == 1.0
    assert metrics.rank_correlation == 1.0


def test_mae_and_rmse_computed_correctly():
    predicted = {"a": 10.0, "b": 20.0}
    actual = {"a": 12.0, "b": 16.0}  # errors: +2, -4
    metrics = evaluate_projection_source("external_baseline", predicted, actual)
    assert metrics.mae == 3.0  # (2 + 4) / 2
    assert metrics.rmse == round(((4 + 16) / 2) ** 0.5, 3)


def test_only_overlapping_ids_are_evaluated():
    predicted = {"a": 10.0, "b": 20.0, "extra": 99.0}
    actual = {"a": 10.0, "b": 20.0}
    metrics = evaluate_projection_source("adjusted", predicted, actual)
    assert metrics.n == 2


def test_no_overlap_returns_all_none_not_an_error():
    metrics = evaluate_projection_source("adjusted", {"a": 10.0}, {"z": 5.0})
    assert metrics.n == 0
    assert metrics.mae is None
    assert metrics.rmse is None
    assert metrics.correlation is None
    assert metrics.rank_correlation is None


def test_constant_series_has_no_defined_correlation():
    predicted = {"a": 10.0, "b": 10.0, "c": 10.0}
    actual = {"a": 5.0, "b": 8.0, "c": 12.0}
    metrics = evaluate_projection_source("independent", predicted, actual)
    assert metrics.correlation is None


def test_top_n_hit_rate_requires_at_least_n_players():
    metrics = evaluate_projection_source("independent", {"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0})
    assert metrics.top5_hit_rate is None
    assert metrics.top10_hit_rate is None


def test_top_n_hit_rate_full_agreement():
    ids = [f"p{i}" for i in range(5)]
    predicted = {pid: float(10 - i) for i, pid in enumerate(ids)}
    actual = dict(predicted)
    metrics = evaluate_projection_source("independent", predicted, actual)
    assert metrics.top5_hit_rate == 1.0


def test_compare_projection_sources_returns_one_metrics_record_per_source():
    actual = {"a": 10.0, "b": 20.0}
    results = compare_projection_sources(
        {"external_baseline": {"a": 9.0, "b": 21.0}, "independent": {"a": 10.0, "b": 20.0}, "adjusted": {"a": 10.5, "b": 19.5}},
        actual,
    )
    assert {r.source for r in results} == {"external_baseline", "independent", "adjusted"}
    independent = next(r for r in results if r.source == "independent")
    assert independent.mae == 0.0
