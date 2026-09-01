"""M1N -- promotion contract tests."""

from canonical.promotion import (
    CURRENT,
    FETCHED,
    NORMALIZED,
    PROMOTABLE,
    RAW_STORED,
    decide_promotion,
)


def test_http_failure_stops_at_fetched():
    decision = decide_promotion(raw_capture_succeeded=False, normalization_succeeded=False, structural_validation_passed=False, provenance_realism_passed=False)
    assert decision.may_promote is False
    assert decision.reached_stage == FETCHED


def test_raw_preserved_even_if_normalization_fails():
    decision = decide_promotion(raw_capture_succeeded=True, normalization_succeeded=False, structural_validation_passed=False, provenance_realism_passed=False)
    assert decision.may_promote is False
    assert decision.reached_stage == RAW_STORED


def test_structural_validation_failure_never_promotes():
    decision = decide_promotion(raw_capture_succeeded=True, normalization_succeeded=True, structural_validation_passed=False, provenance_realism_passed=True)
    assert decision.may_promote is False
    assert decision.reached_stage == NORMALIZED


def test_realism_validation_failure_never_promotes():
    decision = decide_promotion(raw_capture_succeeded=True, normalization_succeeded=True, structural_validation_passed=True, provenance_realism_passed=False)
    assert decision.may_promote is False
    assert decision.reached_stage == NORMALIZED


def test_all_layers_passing_allows_promotion():
    decision = decide_promotion(raw_capture_succeeded=True, normalization_succeeded=True, structural_validation_passed=True, provenance_realism_passed=True)
    assert decision.may_promote is True
    assert decision.reached_stage == PROMOTABLE


def test_validation_failure_decision_carries_no_reference_to_clear_current():
    # decide_promotion never receives or returns anything resembling
    # "clear CURRENT" -- a caller that only writes CURRENT when
    # may_promote is True cannot accidentally erase a prior valid state.
    decision = decide_promotion(raw_capture_succeeded=True, normalization_succeeded=True, structural_validation_passed=False, provenance_realism_passed=True)
    assert not hasattr(decision, "clear_current")
    assert decision.may_promote is False
