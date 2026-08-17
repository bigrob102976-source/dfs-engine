from evaluation.native_component_evaluation import evaluate_hitter_components, evaluate_pitcher_components


def _native_pitcher(player_id, strikeouts, walks, hits_allowed, earned_runs, innings_pitched):
    return {
        "player_id": player_id,
        "player_type": "pitcher",
        "pitcher_components": {
            "strikeouts": {"expected_count": strikeouts},
            "walks": {"expected_count": walks},
            "hits_allowed": {"expected_count": hits_allowed},
            "earned_runs": {"expected_count": earned_runs},
            "innings_pitched": {"expected_count": innings_pitched},
        },
    }


def _actual_pitcher(player_id, status, **overrides):
    base = dict(player_id=player_id, status=status, strikeouts=None, walks=None, hits_allowed=None, earned_runs=None, outs=None)
    base.update(overrides)
    return base


def _native_hitter(player_id, home_runs, walks, stolen_bases):
    return {
        "player_id": player_id,
        "player_type": "hitter",
        "hitter_components": {
            "home_runs": {"expected_count": home_runs},
            "walks": {"expected_count": walks},
            "stolen_bases": {"expected_count": stolen_bases},
        },
    }


def _actual_hitter(player_id, status, **overrides):
    base = dict(player_id=player_id, status=status, home_runs=None, walks=None, stolen_bases=None)
    base.update(overrides)
    return base


# ----------------------------------------------------------------------------
# Pitcher components
# ----------------------------------------------------------------------------


def test_pitcher_strikeout_component_mae_computed_correctly():
    native = [_native_pitcher("1", strikeouts=7.0, walks=2.0, hits_allowed=5.0, earned_runs=2.5, innings_pitched=6.0)]
    actual = [_actual_pitcher("1", "completed_start", strikeouts=9, walks=1, hits_allowed=6, earned_runs=3, outs=18)]
    results = evaluate_pitcher_components(native, actual)
    k_result = next(r for r in results if r.component == "strikeouts")
    assert k_result.n == 1
    assert k_result.mae == 2.0
    assert k_result.mean_predicted == 7.0
    assert k_result.mean_actual == 9.0


def test_pitcher_innings_component_uses_decimal_innings_from_outs():
    native = [_native_pitcher("1", strikeouts=7.0, walks=2.0, hits_allowed=5.0, earned_runs=2.5, innings_pitched=6.0)]
    actual = [_actual_pitcher("1", "completed_start", outs=19)]  # 6.1 innings
    results = evaluate_pitcher_components(native, actual)
    ip_result = next(r for r in results if r.component == "innings_pitched")
    assert ip_result.n == 1
    assert abs(ip_result.mean_actual - (19 / 3.0)) < 1e-3


def test_pitcher_components_excludes_non_scoreable_statuses():
    native = [_native_pitcher("1", strikeouts=7.0, walks=2.0, hits_allowed=5.0, earned_runs=2.5, innings_pitched=6.0)]
    actual = [_actual_pitcher("1", "scratched", strikeouts=None)]
    results = evaluate_pitcher_components(native, actual)
    for r in results:
        assert r.n == 0


def test_pitcher_components_averages_across_multiple_players():
    native = [
        _native_pitcher("1", strikeouts=7.0, walks=2.0, hits_allowed=5.0, earned_runs=2.5, innings_pitched=6.0),
        _native_pitcher("2", strikeouts=5.0, walks=3.0, hits_allowed=6.0, earned_runs=3.0, innings_pitched=5.0),
    ]
    actual = [
        _actual_pitcher("1", "completed_start", strikeouts=9, walks=1, hits_allowed=6, earned_runs=3, outs=18),
        _actual_pitcher("2", "completed_start", strikeouts=3, walks=4, hits_allowed=7, earned_runs=4, outs=15),
    ]
    results = evaluate_pitcher_components(native, actual)
    k_result = next(r for r in results if r.component == "strikeouts")
    assert k_result.n == 2
    assert k_result.mean_predicted == 6.0
    assert k_result.mean_actual == 6.0


def test_empty_inputs_return_zero_n_not_a_crash():
    results = evaluate_pitcher_components([], [])
    assert all(r.n == 0 and r.mae is None for r in results)


# ----------------------------------------------------------------------------
# Hitter components
# ----------------------------------------------------------------------------


def test_hitter_home_run_component_mae_computed_correctly():
    native = [_native_hitter("1", home_runs=0.15, walks=0.4, stolen_bases=0.05)]
    actual = [_actual_hitter("1", "appeared", home_runs=1, walks=0, stolen_bases=0)]
    results = evaluate_hitter_components(native, actual)
    hr_result = next(r for r in results if r.component == "home_runs")
    assert hr_result.n == 1
    assert abs(hr_result.mae - 0.85) < 1e-6


def test_hitter_components_excludes_scratched():
    native = [_native_hitter("1", home_runs=0.15, walks=0.4, stolen_bases=0.05)]
    actual = [_actual_hitter("1", "scratched", home_runs=None)]
    results = evaluate_hitter_components(native, actual)
    for r in results:
        assert r.n == 0


def test_hitter_components_calibration_check_across_many_players():
    # Aggregate calibration: mean predicted HR rate should be close to mean
    # actual HR rate across many players even though no single player's
    # binary HR outcome matches their small predicted probability.
    native = [_native_hitter(str(i), home_runs=0.03, walks=0.4, stolen_bases=0.05) for i in range(20)]
    actual = [_actual_hitter(str(i), "appeared", home_runs=(1 if i == 0 else 0), walks=0, stolen_bases=0) for i in range(20)]
    results = evaluate_hitter_components(native, actual)
    hr_result = next(r for r in results if r.component == "home_runs")
    assert hr_result.n == 20
    assert abs(hr_result.mean_predicted - 0.03) < 1e-6
    assert abs(hr_result.mean_actual - 0.05) < 1e-6
