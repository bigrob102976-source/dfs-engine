from projection_engine.models import SignalContribution
from projection_engine.reasons import build_ai_summary, build_reasons_list, format_signal_reason


def _signal(category="weather", label="Weather", delta=0.42, reason="Wind Out 14 MPH"):
    return SignalContribution(category=category, label=label, raw_delta=delta, weight=1.0, delta=delta, reason=reason)


def test_format_signal_reason_matches_milestone_worked_example_style():
    signal = _signal(delta=0.42, reason="Wind Out 14 MPH")
    assert format_signal_reason(signal) == "Weather +0.42: Wind Out 14 MPH"


def test_format_signal_reason_negative_sign():
    signal = _signal(category="ownership", label="Ownership", delta=-0.14, reason="Extremely popular tournament play")
    assert format_signal_reason(signal) == "Ownership -0.14: Extremely popular tournament play"


def test_build_reasons_list_ranks_by_magnitude_descending():
    signals = [_signal(delta=0.10, reason="small"), _signal(delta=0.45, reason="big"), _signal(delta=-0.30, reason="medium")]
    reasons = build_reasons_list(signals)
    assert "big" in reasons[0]
    assert "medium" in reasons[1]
    assert "small" in reasons[2]


def test_build_reasons_list_caps_at_max_reasons():
    from config.projection_engine_config import MAX_REASONS_PER_PLAYER

    signals = [_signal(delta=0.01 * i, reason=f"signal-{i}") for i in range(1, 20)]
    reasons = build_reasons_list(signals)
    assert len(reasons) == MAX_REASONS_PER_PLAYER


def test_build_reasons_list_drops_zero_delta_signals():
    signals = [_signal(delta=0.0, reason="noop"), _signal(delta=0.20, reason="real")]
    reasons = build_reasons_list(signals)
    assert len(reasons) == 1
    assert "real" in reasons[0]


def test_build_reasons_list_empty_input():
    assert build_reasons_list([]) == []


# ----------------------------------------------------------------------------
# build_ai_summary
# ----------------------------------------------------------------------------


def test_summary_with_no_projection():
    summary = build_ai_summary("Test Player", None, None, None, [])
    assert "Test Player" in summary
    assert "no AI Projection" in summary


def test_summary_positive_only():
    signals = [_signal(category="weather", label="Weather", delta=0.4, reason="x"), _signal(category="vegas", label="Vegas", delta=0.3, reason="y")]
    summary = build_ai_summary("Aaron Judge", 13.6, 91.0, 28.0, signals)
    assert "Aaron Judge" in summary
    assert "13.6" in summary
    assert "confidence 91" in summary
    assert "risk 28" in summary
    assert "positive Weather and Vegas" in summary
    assert "offset by" not in summary


def test_summary_mixed_positive_and_negative():
    signals = [
        _signal(category="weather", label="Weather", delta=0.4, reason="x"),
        _signal(category="vegas", label="Vegas", delta=0.3, reason="y"),
        _signal(category="park", label="Park", delta=0.2, reason="z"),
        _signal(category="ownership", label="Ownership", delta=-0.14, reason="w"),
        _signal(category="matchup", label="Pitcher Matchup", delta=0.15, reason="v"),
    ]
    summary = build_ai_summary("Aaron Judge", 13.6, 91.0, 28.0, signals)
    assert "positive" in summary and "offset by Ownership" in summary


def test_summary_negative_only():
    signals = [_signal(category="ownership", label="Ownership", delta=-0.14, reason="x")]
    summary = build_ai_summary("Test Player", 10.0, 80.0, 30.0, signals)
    assert "negative Ownership" in summary


def test_summary_no_material_signals():
    summary = build_ai_summary("Test Player", 10.0, 80.0, 30.0, [])
    assert "no material signal adjustments" in summary


def test_summary_caps_signals_shown():
    from config.projection_engine_config import MAX_SIGNALS_IN_AI_SUMMARY

    signals = [_signal(category=f"c{i}", label=f"Signal{i}", delta=0.01 * (i + 1), reason=f"r{i}") for i in range(10)]
    summary = build_ai_summary("Test Player", 10.0, 80.0, 30.0, signals)
    shown = sum(1 for s in signals[-MAX_SIGNALS_IN_AI_SUMMARY:] if s.label in summary)
    assert shown == MAX_SIGNALS_IN_AI_SUMMARY
