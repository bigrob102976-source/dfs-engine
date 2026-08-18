from research.game_environment.providers.coverage import (
    EVENT_MATCHED_NO_MONEYLINE,
    EVENT_MATCHED_NO_TOTAL,
    EVENT_NOT_MATCHED,
    NOT_CONFIGURED,
    PLAN_RESTRICTED,
    PREGAME_NOT_AVAILABLE,
    PROVIDER_ERROR,
    UNKNOWN,
    classify_missing_reason,
)


def _base(**overrides):
    defaults = dict(
        is_configured=True, event_matched=True, has_total=True, has_moneyline=True,
        is_pregame=True, provider_errored=False, rate_limited=False,
    )
    defaults.update(overrides)
    return defaults


def test_not_configured_wins_over_everything():
    assert classify_missing_reason(**_base(is_configured=False)) == NOT_CONFIGURED


def test_rate_limited_classified_plan_restricted():
    assert classify_missing_reason(**_base(rate_limited=True)) == PLAN_RESTRICTED


def test_provider_errored_classified_provider_error():
    assert classify_missing_reason(**_base(provider_errored=True)) == PROVIDER_ERROR


def test_event_not_matched():
    assert classify_missing_reason(**_base(event_matched=False)) == EVENT_NOT_MATCHED


def test_pregame_not_available():
    assert classify_missing_reason(**_base(is_pregame=False)) == PREGAME_NOT_AVAILABLE


def test_no_total():
    assert classify_missing_reason(**_base(has_total=False)) == EVENT_MATCHED_NO_TOTAL


def test_no_moneyline():
    assert classify_missing_reason(**_base(has_moneyline=False)) == EVENT_MATCHED_NO_MONEYLINE


def test_everything_present_is_unknown_fallthrough_not_a_false_valid():
    # classify_missing_reason is only ever called when something's
    # already wrong (e.g. no run line) -- it never asserts VALID itself.
    assert classify_missing_reason(**_base()) == UNKNOWN
