import pytest

from research.game_environment.bullpen import (
    BullpenProvider,
    MockBullpenProvider,
    fatigue_label,
    score_bullpen_strength,
)


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BullpenProvider()


def test_mock_provider_implements_interface():
    assert isinstance(MockBullpenProvider(), BullpenProvider)


def test_mock_provider_is_always_configured():
    assert MockBullpenProvider().is_configured() is True


def test_mock_provider_name_is_clearly_labeled():
    assert MockBullpenProvider().provider_name() == "MOCK BULLPEN DATA"


def test_mock_bullpen_is_deterministic_not_random():
    provider = MockBullpenProvider()
    first = provider.get_bullpen("PHI")
    second = provider.get_bullpen("PHI")
    assert first.era == second.era
    assert first.strength_score == second.strength_score


def test_mock_bullpen_differs_by_team():
    provider = MockBullpenProvider()
    a = provider.get_bullpen("PHI")
    b = provider.get_bullpen("COL")
    assert a.era != b.era or a.strength_score != b.strength_score


def test_mock_bullpen_has_a_strength_score_in_range():
    profile = MockBullpenProvider().get_bullpen("PHI")
    assert profile.strength_score is not None
    assert 0.0 <= profile.strength_score <= 100.0


def test_provenance_fields_present():
    profile = MockBullpenProvider().get_bullpen("PHI")
    assert profile.provider_name == "MOCK BULLPEN DATA"
    assert profile.is_mock is True
    assert profile.team_abbr == "PHI"


# ----------------------------------------------------------------------------
# score_bullpen_strength
# ----------------------------------------------------------------------------


def test_strong_era_and_fip_produce_a_high_score():
    score = score_bullpen_strength(era=2.50, fip=2.50, relievers_used_last_3_days=0, closer_available=True)
    assert score >= 90.0


def test_weak_era_and_fip_produce_a_low_score():
    score = score_bullpen_strength(era=5.50, fip=5.50, relievers_used_last_3_days=6, closer_available=False)
    assert score <= 15.0


def test_missing_all_inputs_returns_none_never_a_guess():
    assert score_bullpen_strength(era=None, fip=None, relievers_used_last_3_days=None, closer_available=None) is None


def test_partial_inputs_still_produce_a_score():
    score = score_bullpen_strength(era=3.00, fip=None, relievers_used_last_3_days=None, closer_available=None)
    assert score is not None


def test_score_is_always_clamped_to_0_100():
    score = score_bullpen_strength(era=1.00, fip=1.00, relievers_used_last_3_days=0, closer_available=True)
    assert score <= 100.0
    score = score_bullpen_strength(era=9.00, fip=9.00, relievers_used_last_3_days=10, closer_available=False)
    assert score >= 0.0


# ----------------------------------------------------------------------------
# fatigue_label
# ----------------------------------------------------------------------------


def test_fatigue_label_bands():
    assert fatigue_label(None) == "unknown"
    assert fatigue_label(0) == "low"
    assert fatigue_label(1) == "medium"
    assert fatigue_label(2) == "medium"
    assert fatigue_label(3) == "high"
    assert fatigue_label(5) == "high"
