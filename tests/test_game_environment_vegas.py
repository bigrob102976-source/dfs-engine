import pytest

from research.game_environment.models import VegasLine, VegasSnapshot
from research.game_environment.vegas import (
    MockVegasProvider,
    VegasProvider,
    analyze_vegas_slate,
    total_tier,
)


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        VegasProvider()


def test_mock_provider_implements_interface():
    assert isinstance(MockVegasProvider(), VegasProvider)


def test_mock_provider_is_always_configured():
    assert MockVegasProvider().is_configured() is True


def test_mock_provider_name_is_clearly_labeled():
    assert MockVegasProvider().provider_name() == "MOCK VEGAS"


def test_mock_vegas_is_deterministic_not_random():
    provider = MockVegasProvider()
    first = provider.get_vegas_line("g1", "PHI", "COL")
    second = provider.get_vegas_line("g1", "PHI", "COL")
    assert first.current_home.total == second.current_home.total
    assert first.current_home.moneyline == second.current_home.moneyline


def test_mock_vegas_differs_by_game_id():
    provider = MockVegasProvider()
    a = provider.get_vegas_line("g1", "PHI", "COL")
    b = provider.get_vegas_line("g2", "PHI", "COL")
    assert a.current_home.total != b.current_home.total or a.current_home.moneyline != b.current_home.moneyline


def test_mock_vegas_has_opening_and_current_lines_with_movement():
    provider = MockVegasProvider()
    snapshot = provider.get_vegas_line("g1", "PHI", "COL")
    assert snapshot.opening_home.total is not None
    assert snapshot.current_home.total is not None
    assert snapshot.total_movement == round(snapshot.current_home.total - snapshot.opening_home.total, 1)
    assert snapshot.moneyline_movement_home == snapshot.current_home.moneyline - snapshot.opening_home.moneyline


def test_mock_vegas_implied_runs_sum_to_the_total():
    provider = MockVegasProvider()
    snapshot = provider.get_vegas_line("g1", "PHI", "COL")
    assert round(snapshot.home_implied_runs + snapshot.away_implied_runs, 1) == snapshot.current_home.total


def test_mock_vegas_moneylines_are_opposite_signed_favorite_dog():
    provider = MockVegasProvider()
    snapshot = provider.get_vegas_line("g1", "PHI", "COL")
    home_ml = snapshot.current_home.moneyline
    away_ml = snapshot.current_away.moneyline
    assert (home_ml < 0) != (away_ml < 0)  # exactly one side is the favorite


def test_provenance_fields_present():
    provider = MockVegasProvider()
    snapshot = provider.get_vegas_line("g1", "PHI", "COL")
    assert snapshot.provider_name == "MOCK VEGAS"
    assert snapshot.is_mock is True
    assert snapshot.retrieved_at
    assert snapshot.home_team == "PHI"
    assert snapshot.away_team == "COL"


# ----------------------------------------------------------------------------
# analyze_vegas_slate
# ----------------------------------------------------------------------------


def _snapshot(game_id, home="AAA", away="BBB", total=9.0, home_ml=-150, movement=0.0) -> VegasSnapshot:
    away_ml = 130 if home_ml < 0 else -150
    return VegasSnapshot(
        game_id=game_id, home_team=home, away_team=away, provider_name="MOCK VEGAS", is_mock=True, retrieved_at="now",
        opening_home=VegasLine(moneyline=home_ml, run_line=-1.5, total=total - movement),
        opening_away=VegasLine(moneyline=away_ml, run_line=1.5, total=total - movement),
        current_home=VegasLine(moneyline=home_ml, run_line=-1.5, total=total),
        current_away=VegasLine(moneyline=away_ml, run_line=1.5, total=total),
        home_implied_runs=total / 2, away_implied_runs=total / 2,
        total_movement=movement, moneyline_movement_home=0,
    )


def test_empty_snapshot_list_returns_a_blank_analysis():
    analysis = analyze_vegas_slate([])
    assert analysis.highest_total_game_id is None
    assert analysis.sharp_movement_game_ids == []


def test_identifies_highest_and_lowest_total():
    snapshots = [_snapshot("g1", total=7.0), _snapshot("g2", total=11.5), _snapshot("g3", total=9.0)]
    analysis = analyze_vegas_slate(snapshots)
    assert analysis.highest_total_game_id == "g2"
    assert analysis.lowest_total_game_id == "g1"


def test_identifies_largest_line_movement():
    snapshots = [_snapshot("g1", movement=0.2), _snapshot("g2", movement=-1.5), _snapshot("g3", movement=0.5)]
    analysis = analyze_vegas_slate(snapshots)
    assert analysis.largest_movement_game_id == "g2"


def test_identifies_biggest_favorite_and_underdog():
    snapshots = [_snapshot("g1", home_ml=-120), _snapshot("g2", home_ml=-300), _snapshot("g3", home_ml=250)]
    analysis = analyze_vegas_slate(snapshots)
    assert analysis.biggest_favorite_game_id == "g2"
    assert analysis.biggest_underdog_game_id == "g3"


def test_sharp_movement_flags_games_at_or_above_the_threshold():
    snapshots = [_snapshot("g1", movement=0.5), _snapshot("g2", movement=1.0), _snapshot("g3", movement=-1.2)]
    analysis = analyze_vegas_slate(snapshots)
    assert set(analysis.sharp_movement_game_ids) == {"g2", "g3"}


def test_total_tier_bands():
    assert total_tier(10.5) == "high"
    assert total_tier(7.0) == "low"
    assert total_tier(8.5) == "medium"
    assert total_tier(None) == "medium"
