from config import native_projection_config as cfg
from models.batter import BatterInput, RecentBattingStats, SeasonBattingStats

from native_projections.hitter_rates import project_hitter_rates


def make_batter(season=None, recent=None, **top):
    defaults = dict(player_id="B1", name="Test Hitter", team="AAA", opponent="BBB", batting_order=3)
    defaults.update(top)
    return BatterInput(
        **defaults,
        season=SeasonBattingStats(**(season or {})),
        recent=RecentBattingStats(**(recent or {})),
    )


# ----------------------------------------------------------------------------
# The documented Andrew Pinckney-type small-sample issue
# ----------------------------------------------------------------------------


def test_tiny_sample_home_run_gets_heavily_regressed_toward_league_average():
    # 10 PA, 1 HR -> a naive rate would be 0.10 (10%), wildly above the
    # league-average HR rate of 0.032. Regression must pull this most of
    # the way back toward league average, not let the raw rate stand.
    pinckney = make_batter(
        season=dict(plate_appearances=10, at_bats=9, hits=1, doubles=0, triples=0, home_runs=1, walks=1, strikeouts=2, stolen_bases=0)
    )
    rates = project_hitter_rates(pinckney)
    naive_rate = 1 / 10
    league_avg = cfg.LEAGUE_AVG_HITTER_RATES["home_run_rate"]
    assert rates.home_run_rate < naive_rate
    # regressed rate should land much closer to league average than to the naive rate
    assert abs(rates.home_run_rate - league_avg) < abs(rates.home_run_rate - naive_rate)


def test_tiny_sample_gets_much_more_regression_than_large_sample():
    tiny = make_batter(season=dict(plate_appearances=10, hits=1, doubles=0, triples=0, home_runs=1, walks=1, strikeouts=2))
    regular = make_batter(
        season=dict(plate_appearances=550, hits=140, doubles=28, triples=3, home_runs=25, walks=50, strikeouts=110, stolen_bases=8)
    )
    tiny_rates = project_hitter_rates(tiny)
    regular_rates = project_hitter_rates(regular)
    league_avg = cfg.LEAGUE_AVG_HITTER_RATES["home_run_rate"]
    tiny_shift = abs(tiny_rates.home_run_rate - league_avg)
    regular_naive = 25 / 550
    regular_shift = abs(regular_rates.home_run_rate - regular_naive)
    # the large-sample player's regressed rate stays much closer to their
    # own observed rate than the tiny-sample player's does
    assert regular_shift < tiny_shift


def test_large_sample_stays_close_to_observed_rate():
    regular = make_batter(
        season=dict(plate_appearances=550, hits=140, doubles=28, triples=3, home_runs=25, walks=50, strikeouts=110, stolen_bases=8)
    )
    rates = project_hitter_rates(regular)
    naive_hr_rate = 25 / 550
    assert abs(rates.home_run_rate - naive_hr_rate) < 0.01


# ----------------------------------------------------------------------------
# Recency blending (K/BB only)
# ----------------------------------------------------------------------------


def test_recent_k_rate_blends_with_season_when_recent_data_present():
    b = make_batter(
        season=dict(plate_appearances=400, strikeouts=80),  # 20% season K rate
        recent=dict(plate_appearances=50, k_percent=40.0),  # hot-streak-of-strikeouts recently
    )
    rates = project_hitter_rates(b)
    season_only = make_batter(season=dict(plate_appearances=400, strikeouts=80))
    season_only_rates = project_hitter_rates(season_only)
    assert rates.strikeout_rate > season_only_rates.strikeout_rate


def test_no_recent_data_falls_back_to_season_only():
    b = make_batter(season=dict(plate_appearances=400, strikeouts=80, walks=40))
    rates = project_hitter_rates(b)
    assert any("season-only" in r for r in rates.reasons)


def test_recent_blend_weight_is_capped():
    # A huge recent sample should still not fully override the season rate --
    # the blend weight is capped at cfg.MAX_RECENT_BLEND_WEIGHT.
    season_only = make_batter(season=dict(plate_appearances=400, strikeouts=80))
    season_only_rate = project_hitter_rates(season_only).strikeout_rate

    b = make_batter(
        season=dict(plate_appearances=400, strikeouts=80),
        recent=dict(plate_appearances=1000, k_percent=90.0),
    )
    rates = project_hitter_rates(b)
    max_possible = (1 - cfg.MAX_RECENT_BLEND_WEIGHT) * season_only_rate + cfg.MAX_RECENT_BLEND_WEIGHT * 0.90
    assert rates.strikeout_rate <= max_possible + 1e-3
    assert rates.strikeout_rate < 0.90


# ----------------------------------------------------------------------------
# Honest gaps (HBP, missing data)
# ----------------------------------------------------------------------------


def test_hbp_rate_always_league_average_and_flagged():
    b = make_batter(season=dict(plate_appearances=400, hits=100))
    rates = project_hitter_rates(b)
    assert rates.hit_by_pitch_rate == cfg.LEAGUE_AVG_HITTER_RATES["hbp_rate"]
    assert any("not tracked" in r.lower() for r in rates.reasons)


def test_missing_season_data_falls_back_entirely_to_league_averages():
    b = make_batter()
    rates = project_hitter_rates(b)
    league = cfg.LEAGUE_AVG_HITTER_RATES
    assert rates.home_run_rate == round(league["home_run_rate"], 4)
    assert rates.strikeout_rate == round(league["k_rate"], 4)
    assert rates.walk_rate == round(league["bb_rate"], 4)


def test_coverage_tracks_missing_fields():
    b = make_batter()
    rates = project_hitter_rates(b)
    assert rates.coverage_fields_available == 0
    assert rates.coverage_fields_total > 0
    assert "season.plate_appearances" in rates.coverage_missing_fields
    assert "season.hit_by_pitch" in rates.coverage_missing_fields


def test_coverage_improves_with_more_data():
    sparse = make_batter()
    full = make_batter(
        season=dict(plate_appearances=400, strikeouts=80, walks=40, hits=100, doubles=20, triples=2, home_runs=15, stolen_bases=5),
        recent=dict(plate_appearances=50, k_percent=20.0, bb_percent=9.0),
    )
    sparse_rates = project_hitter_rates(sparse)
    full_rates = project_hitter_rates(full)
    assert full_rates.coverage_fields_available > sparse_rates.coverage_fields_available


# ----------------------------------------------------------------------------
# Hit-type derivation
# ----------------------------------------------------------------------------


def test_singles_derived_from_hits_minus_extra_base_hits():
    b = make_batter(season=dict(plate_appearances=500, hits=150, doubles=30, triples=5, home_runs=20))
    rates = project_hitter_rates(b)
    naive_singles = 150 - 30 - 5 - 20
    naive_single_rate = naive_singles / 500
    assert abs(rates.single_rate - naive_single_rate) < 0.02
