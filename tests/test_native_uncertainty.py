from config import native_projection_config as cfg

from native_projections.dk_scoring import hitter_components, hitter_base_projection, pitcher_components, pitcher_base_projection
from native_projections.hitter_rates import HitterRates
from native_projections.pitcher_rates import PitcherRates
from native_projections.playing_time import PitcherOpportunity
from native_projections.uncertainty import compute_confidence, hitter_uncertainty, pitcher_uncertainty


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
# Hitter uncertainty
# ----------------------------------------------------------------------------


def test_hitter_ceiling_above_projection_and_floor_below():
    rates = make_hitter_rates()
    components = hitter_components(rates, expected_pa=4.3, batting_order=3)
    projection = hitter_base_projection(components)
    result = hitter_uncertainty(rates, expected_pa=4.3, base_projection=projection, pa_confidence=90.0, season_pa=500, recent_pa=50, completeness_fraction=0.9)
    assert result.ceiling > projection
    assert result.floor < projection
    assert result.floor >= cfg.MIN_FLOOR_POINTS


def test_hitter_floor_never_negative_for_tiny_projection():
    rates = make_hitter_rates(single_rate=0.01, double_rate=0.0, triple_rate=0.0, home_run_rate=0.0, walk_rate=0.0, hit_by_pitch_rate=0.0, stolen_base_rate=0.0)
    components = hitter_components(rates, expected_pa=1.0, batting_order=9)
    projection = hitter_base_projection(components)
    result = hitter_uncertainty(rates, expected_pa=1.0, base_projection=projection, pa_confidence=0.0, season_pa=10, recent_pa=None, completeness_fraction=0.2)
    assert result.floor >= cfg.MIN_FLOOR_POINTS


def test_hitter_higher_power_rate_widens_ceiling_floor_spread():
    low_power = make_hitter_rates(home_run_rate=0.01)
    high_power = make_hitter_rates(home_run_rate=0.10)
    low_components = hitter_components(low_power, expected_pa=4.3, batting_order=3)
    high_components = hitter_components(high_power, expected_pa=4.3, batting_order=3)
    low_proj = hitter_base_projection(low_components)
    high_proj = hitter_base_projection(high_components)
    low_result = hitter_uncertainty(low_power, 4.3, low_proj, 90.0, 500, 50, 0.9)
    high_result = hitter_uncertainty(high_power, 4.3, high_proj, 90.0, 500, 50, 0.9)
    assert (high_result.ceiling - high_result.floor) > (low_result.ceiling - low_result.floor)


def test_hitter_uncertainty_handles_zero_expected_pa_without_crashing():
    rates = make_hitter_rates()
    components = hitter_components(rates, expected_pa=0.0, batting_order=9)
    projection = hitter_base_projection(components)
    result = hitter_uncertainty(rates, expected_pa=0.0, base_projection=projection, pa_confidence=0.0, season_pa=None, recent_pa=None, completeness_fraction=0.0)
    assert result.ceiling >= result.floor
    assert result.floor >= cfg.MIN_FLOOR_POINTS


# ----------------------------------------------------------------------------
# Pitcher uncertainty
# ----------------------------------------------------------------------------


def test_pitcher_ceiling_above_projection_and_floor_below():
    rates = make_pitcher_rates()
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    components = pitcher_components(rates, opp)
    projection = pitcher_base_projection(components)
    result = pitcher_uncertainty(rates, opp, projection, season_bf=600, recent_bf=70, completeness_fraction=0.9)
    assert result.ceiling > projection
    assert result.floor < projection
    assert result.floor >= cfg.MIN_FLOOR_POINTS


def test_pitcher_higher_strikeout_rate_widens_spread():
    opp = PitcherOpportunity(expected_innings=6.0, expected_batters_faced=25.8, expected_pitch_count=95.0, workload_confidence=85.0)
    low_k = make_pitcher_rates(strikeout_rate=0.14)
    high_k = make_pitcher_rates(strikeout_rate=0.34)
    low_components = pitcher_components(low_k, opp)
    high_components = pitcher_components(high_k, opp)
    low_proj = pitcher_base_projection(low_components)
    high_proj = pitcher_base_projection(high_components)
    low_result = pitcher_uncertainty(low_k, opp, low_proj, 600, 70, 0.9)
    high_result = pitcher_uncertainty(high_k, opp, high_proj, 600, 70, 0.9)
    assert (high_result.ceiling - high_result.floor) > (low_result.ceiling - low_result.floor)


# ----------------------------------------------------------------------------
# compute_confidence
# ----------------------------------------------------------------------------


def test_confidence_increases_with_more_season_opportunities():
    low = compute_confidence(20, 60.0, None, 40.0, 0.5)
    high = compute_confidence(600, 60.0, None, 40.0, 0.5)
    assert high > low


def test_confidence_increases_with_more_recent_opportunities():
    low = compute_confidence(400, 60.0, 5, 40.0, 0.5)
    high = compute_confidence(400, 60.0, 60, 40.0, 0.5)
    assert high > low


def test_confidence_increases_with_completeness():
    low = compute_confidence(400, 60.0, 40, 40.0, 0.1)
    high = compute_confidence(400, 60.0, 40, 40.0, 1.0)
    assert high > low


def test_confidence_respects_min_and_max_bounds():
    zero = compute_confidence(None, 60.0, None, 40.0, 0.0)
    maxed = compute_confidence(10000, 60.0, 10000, 40.0, 1.0)
    assert zero >= cfg.MIN_CONFIDENCE
    assert maxed <= cfg.MAX_CONFIDENCE
