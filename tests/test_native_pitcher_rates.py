from config import native_projection_config as cfg
from models.pitcher import PitcherInput, RecentStats, SeasonStats

from native_projections.pitcher_rates import project_pitcher_rates


def make_pitcher(season=None, recent=None, **top):
    defaults = dict(player_id="P1", name="Test Pitcher", team="AAA", opponent="BBB")
    defaults.update(top)
    return PitcherInput(
        **defaults,
        season=SeasonStats(**(season or {})),
        recent=RecentStats(**(recent or {})),
    )


# ----------------------------------------------------------------------------
# Small-sample regression (HR-against, Pinckney-equivalent for pitchers)
# ----------------------------------------------------------------------------


def test_tiny_sample_home_runs_allowed_gets_heavily_regressed():
    tiny = make_pitcher(season=dict(batters_faced=15, home_runs_allowed=2, strikeouts=3, walks=1, hits_allowed=4, innings=3.0))
    rates = project_pitcher_rates(tiny)
    naive_rate = 2 / 15
    league_avg = cfg.LEAGUE_AVG_PITCHER_RATES["home_run_rate"]
    assert rates.home_run_rate < naive_rate
    assert abs(rates.home_run_rate - league_avg) < abs(rates.home_run_rate - naive_rate)


def test_large_sample_stays_close_to_observed_home_run_rate():
    regular = make_pitcher(
        season=dict(batters_faced=700, home_runs_allowed=22, strikeouts=180, walks=55, hits_allowed=140, innings=170.0)
    )
    rates = project_pitcher_rates(regular)
    naive_rate = 22 / 700
    assert abs(rates.home_run_rate - naive_rate) < 0.01


# ----------------------------------------------------------------------------
# Recency blend (K/BB, real counts)
# ----------------------------------------------------------------------------


def test_recent_k_rate_blends_with_season_using_real_counts():
    season_only = make_pitcher(season=dict(batters_faced=400, strikeouts=80, innings=95.0))
    hot = make_pitcher(
        season=dict(batters_faced=400, strikeouts=80, innings=95.0),
        recent=dict(batters_faced=60, strikeouts=25, innings=15.0),
    )
    season_only_rate = project_pitcher_rates(season_only).strikeout_rate
    hot_rate = project_pitcher_rates(hot).strikeout_rate
    assert hot_rate > season_only_rate


def test_no_recent_data_falls_back_to_season_only():
    p = make_pitcher(season=dict(batters_faced=400, strikeouts=80, walks=30, innings=95.0))
    rates = project_pitcher_rates(p)
    assert any("season-only" in r for r in rates.reasons)


# ----------------------------------------------------------------------------
# Backward-compat fallback: percentage-only (pre-Milestone-23 cached data)
# ----------------------------------------------------------------------------


def test_percent_only_season_falls_back_to_approximate_count():
    p = make_pitcher(season=dict(k_percent=25.0, bb_percent=8.0, innings=100.0))
    rates = project_pitcher_rates(p)
    assert any("reconstructed from k_percent" in r for r in rates.reasons)
    # Should land meaningfully close to 25% (partially regressed, not identical)
    assert 0.15 < rates.strikeout_rate < 0.26


def test_no_data_at_all_falls_back_to_league_averages():
    p = make_pitcher()
    rates = project_pitcher_rates(p)
    league = cfg.LEAGUE_AVG_PITCHER_RATES
    assert rates.strikeout_rate == round(league["k_rate"], 4)
    assert rates.home_run_rate == round(league["home_run_rate"], 4)


# ----------------------------------------------------------------------------
# Earned-run rate
# ----------------------------------------------------------------------------


def test_earned_run_rate_uses_real_count_when_available():
    p = make_pitcher(season=dict(earned_runs=70, innings=170.0))
    rates = project_pitcher_rates(p)
    naive = 70 / 170.0
    assert abs(rates.earned_run_rate_per_inning - naive) < 0.05
    assert any("count-based regression" in r for r in rates.reasons)


def test_earned_run_rate_falls_back_to_era_when_no_raw_count():
    p = make_pitcher(season=dict(era=3.60, innings=170.0))
    rates = project_pitcher_rates(p)
    naive = 3.60 / 9.0
    assert abs(rates.earned_run_rate_per_inning - naive) < 0.05
    assert any("reconstructed from season ERA" in r for r in rates.reasons)


def test_earned_run_rate_falls_back_to_league_average_with_no_data():
    p = make_pitcher()
    rates = project_pitcher_rates(p)
    assert rates.earned_run_rate_per_inning == round(cfg.LEAGUE_AVG_EARNED_RUNS_PER_INNING, 4)


# ----------------------------------------------------------------------------
# Coverage tracking
# ----------------------------------------------------------------------------


def test_coverage_tracks_missing_fields():
    p = make_pitcher()
    rates = project_pitcher_rates(p)
    assert rates.coverage_fields_available == 0
    assert "season.batters_faced" in rates.coverage_missing_fields


def test_season_opportunities_uses_real_batters_faced_when_available():
    p = make_pitcher(season=dict(batters_faced=400, strikeouts=80, innings=95.0))
    rates = project_pitcher_rates(p)
    assert rates.season_opportunities == 400.0


def test_season_opportunities_falls_back_to_approximate_when_only_percent_available():
    p = make_pitcher(season=dict(k_percent=25.0, innings=100.0))
    rates = project_pitcher_rates(p)
    assert rates.season_opportunities is not None
    assert rates.season_opportunities == 100.0 * cfg.BATTERS_PER_INNING


def test_season_opportunities_none_when_no_data_at_all():
    p = make_pitcher()
    rates = project_pitcher_rates(p)
    assert rates.season_opportunities is None
    assert rates.recent_opportunities is None


def test_coverage_improves_with_more_data():
    sparse = make_pitcher()
    full = make_pitcher(
        season=dict(batters_faced=400, strikeouts=80, walks=30, hits_allowed=90, home_runs_allowed=10, hit_by_pitch=4, earned_runs=45, innings=95.0),
        recent=dict(batters_faced=60, strikeouts=15, walks=5),
    )
    sparse_rates = project_pitcher_rates(sparse)
    full_rates = project_pitcher_rates(full)
    assert full_rates.coverage_fields_available > sparse_rates.coverage_fields_available
