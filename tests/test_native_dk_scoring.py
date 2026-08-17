from config.batter_scoring_config import DK_HITTER_SCORING
from config.scoring_config import DK_SCORING

from native_projections.dk_scoring import (
    hitter_base_projection,
    hitter_components,
    pitcher_base_projection,
    pitcher_components,
)
from native_projections.hitter_rates import HitterRates
from native_projections.pitcher_rates import PitcherRates
from native_projections.playing_time import PitcherOpportunity


def make_hitter_rates(**overrides):
    defaults = dict(
        single_rate=0.145, double_rate=0.045, triple_rate=0.004, home_run_rate=0.032,
        walk_rate=0.085, hit_by_pitch_rate=0.010, strikeout_rate=0.220, stolen_base_rate=0.012,
    )
    defaults.update(overrides)
    return HitterRates(**defaults)


def make_pitcher_rates(**overrides):
    defaults = dict(
        strikeout_rate=0.220, walk_rate=0.085, hit_rate=0.235, home_run_rate=0.032,
        hit_by_pitch_rate=0.010, earned_run_rate_per_inning=0.467,
    )
    defaults.update(overrides)
    return PitcherRates(**defaults)


# ----------------------------------------------------------------------------
# Hitter components
# ----------------------------------------------------------------------------


def test_single_component_uses_expected_pa_and_dk_value():
    rates = make_hitter_rates()
    components = hitter_components(rates, expected_pa=4.3, batting_order=3)
    expected_singles_count = 4.3 * rates.single_rate
    assert abs(components.singles.expected_count - expected_singles_count) < 1e-3
    assert components.singles.dk_points_per_event == DK_HITTER_SCORING["single"]
    assert abs(components.singles.dk_points - expected_singles_count * DK_HITTER_SCORING["single"]) < 1e-3


def test_leadoff_slot_multiplier_differs_from_bottom_of_order():
    rates = make_hitter_rates()
    leadoff = hitter_components(rates, expected_pa=4.6, batting_order=1)
    ninth = hitter_components(rates, expected_pa=3.7, batting_order=9)
    assert leadoff.runs.dk_points > ninth.runs.dk_points
    assert leadoff.rbi.dk_points > ninth.rbi.dk_points


def test_strikeouts_expected_is_informational_only():
    rates = make_hitter_rates(strikeout_rate=0.30)
    components = hitter_components(rates, expected_pa=4.0, batting_order=3)
    assert components.strikeouts_expected > 0
    # not part of the DK points sum -- HitterComponents has no ComponentValue for it
    assert isinstance(components.strikeouts_expected, float)


def test_hitter_base_projection_sums_all_scored_components():
    rates = make_hitter_rates()
    components = hitter_components(rates, expected_pa=4.3, batting_order=3)
    manual_sum = round(
        components.singles.dk_points + components.doubles.dk_points + components.triples.dk_points
        + components.home_runs.dk_points + components.walks.dk_points + components.hit_by_pitch.dk_points
        + components.stolen_bases.dk_points + components.runs.dk_points + components.rbi.dk_points,
        3,
    )
    assert hitter_base_projection(components) == manual_sum


def test_higher_home_run_rate_increases_base_projection():
    low = hitter_components(make_hitter_rates(home_run_rate=0.02), expected_pa=4.3, batting_order=3)
    high = hitter_components(make_hitter_rates(home_run_rate=0.08), expected_pa=4.3, batting_order=3)
    assert hitter_base_projection(high) > hitter_base_projection(low)


# ----------------------------------------------------------------------------
# Pitcher components
# ----------------------------------------------------------------------------


def test_innings_pitched_component_uses_expected_innings_directly():
    rates = make_pitcher_rates()
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    assert components.innings_pitched.expected_count == 6.0
    assert components.innings_pitched.dk_points == 6.0 * DK_SCORING["innings_pitched"]


def test_strikeout_component_uses_expected_batters_faced_and_rate():
    rates = make_pitcher_rates(strikeout_rate=0.25)
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    expected_k_count = 25.8 * 0.25
    assert abs(components.strikeouts.expected_count - expected_k_count) < 1e-6
    assert components.strikeouts.dk_points_per_event == DK_SCORING["strikeout"]


def test_earned_runs_use_expected_innings_and_er_rate():
    rates = make_pitcher_rates(earned_run_rate_per_inning=0.5)
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    assert abs(components.earned_runs.expected_count - 3.0) < 1e-6
    assert components.earned_runs.dk_points < 0  # earned_run DK value is negative


def test_win_probability_is_none_in_v1():
    rates = make_pitcher_rates()
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    assert components.win_probability is None
    assert components.win_probability_is_mock is None


def test_pitcher_base_projection_sums_all_components():
    rates = make_pitcher_rates()
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    manual_sum = round(
        components.innings_pitched.dk_points + components.strikeouts.dk_points + components.walks.dk_points
        + components.hit_batsmen.dk_points + components.hits_allowed.dk_points + components.earned_runs.dk_points,
        3,
    )
    assert pitcher_base_projection(components) == manual_sum


def test_higher_strikeout_rate_increases_base_projection():
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    low = pitcher_components(make_pitcher_rates(strikeout_rate=0.15), opp)
    high = pitcher_components(make_pitcher_rates(strikeout_rate=0.32), opp)
    assert pitcher_base_projection(high) > pitcher_base_projection(low)
