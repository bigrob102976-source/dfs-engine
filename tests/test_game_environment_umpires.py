import pytest

from research.game_environment.umpires import MockUmpireProvider, UmpireProvider, UnknownUmpireProvider


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        UmpireProvider()


def test_unknown_provider_implements_interface():
    assert isinstance(UnknownUmpireProvider(), UmpireProvider)


def test_mock_provider_implements_interface():
    assert isinstance(MockUmpireProvider(), UmpireProvider)


def test_unknown_provider_is_not_configured():
    assert UnknownUmpireProvider().is_configured() is False


def test_unknown_provider_never_guesses_reports_unknown_status():
    profile = UnknownUmpireProvider().get_umpire("g1")
    assert profile.status == "UNKNOWN"
    assert profile.tendency == "unknown"
    assert profile.name is None
    assert profile.strike_percent is None


def test_unknown_provider_never_raises():
    # Missing umpire data is a normal, expected outcome -- never an error.
    UnknownUmpireProvider().get_umpire("any-game-id")


def test_mock_provider_is_configured_and_labeled():
    provider = MockUmpireProvider()
    assert provider.is_configured() is True
    assert provider.provider_name() == "MOCK UMPIRE DATA"


def test_mock_provider_returns_a_known_profile():
    profile = MockUmpireProvider().get_umpire("g1")
    assert profile.status == "KNOWN"
    assert profile.name is not None
    assert profile.strike_percent is not None
    assert profile.tendency in ("pitcher_friendly", "hitter_friendly", "neutral")


def test_mock_provider_is_deterministic_not_random():
    provider = MockUmpireProvider()
    first = provider.get_umpire("g1")
    second = provider.get_umpire("g1")
    assert first.strike_percent == second.strike_percent
    assert first.name == second.name


def test_mock_provider_differs_by_game_id():
    provider = MockUmpireProvider()
    a = provider.get_umpire("g1")
    b = provider.get_umpire("g2")
    assert a.strike_percent != b.strike_percent or a.zone_size_score != b.zone_size_score
