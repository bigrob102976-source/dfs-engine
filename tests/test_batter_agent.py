from agents.batter_agent import analyze_batter, analyze_slate
from models.batter import (
    BatterInput,
    OpposingPitcherContext,
    PlatoonSplitStats,
    RecentBattingStats,
    SeasonBattingStats,
    TrendMetrics,
)

BASE_SEASON = dict(
    plate_appearances=450, at_bats=400, hits=110, doubles=22, triples=2, home_runs=18,
    walks=45, strikeouts=90, stolen_bases=4,
    avg=0.275, obp=0.355, slg=0.470, ops=0.825,
    k_percent=20.0, bb_percent=10.0, iso=0.195, woba=0.345,
    xwoba=0.340, xba=0.265, xslg=0.460,
    hard_hit_percent=40.0, barrel_percent=8.0, exit_velocity=89.0,
    sweet_spot_percent=34.0, bat_speed=72.0,
)
BASE_RECENT = dict(plate_appearances=50, k_percent=20.0, bb_percent=10.0, xwoba=0.340, exit_velocity=89.0, hard_hit_percent=40.0, barrel_percent=8.0)
BASE_OPPOSING_PITCHER = dict(
    player_id="P1", name="Opp SP", throwing_hand="R", k_percent=22.0, bb_percent=8.0,
    xera=4.00, xwoba_allowed=0.320, hard_hit_percent_allowed=38.0, barrel_percent_allowed=8.0,
    ground_ball_percent=42.0, velocity=93.0, csw_percent=27.0,
)
BASE_VS_RHP = dict(plate_appearances=300, k_percent=19.0, bb_percent=10.0, iso=0.190, woba=0.340, ops=0.820, split_type="vs_hand")
BASE_VS_LHP = dict(plate_appearances=150, k_percent=22.0, bb_percent=9.0, iso=0.210, woba=0.350, ops=0.830, split_type="vs_hand")


def make_batter(season=None, recent=None, opposing_pitcher=None, vs_rhp=None, vs_lhp=None, trends=None, **top):
    defaults = dict(player_id="TEST1", name="Test Hitter", team="AAA", opponent="BBB", batting_order=3, batting_hand="R")
    defaults.update(top)
    return BatterInput(
        **defaults,
        season=SeasonBattingStats(**{**BASE_SEASON, **(season or {})}),
        recent=RecentBattingStats(**{**BASE_RECENT, **(recent or {})}),
        opposing_pitcher=OpposingPitcherContext(**{**BASE_OPPOSING_PITCHER, **(opposing_pitcher or {})}),
        vs_rhp=PlatoonSplitStats(**{**BASE_VS_RHP, **(vs_rhp or {})}),
        vs_lhp=PlatoonSplitStats(**{**BASE_VS_LHP, **(vs_lhp or {})}),
        trends=TrendMetrics(**(trends or {})),
    )


# ----------------------------------------------------------------------------
# Sub-scores
# ----------------------------------------------------------------------------


def test_higher_iso_and_barrel_increase_power_score():
    low = analyze_batter(make_batter(season={"iso": 0.110, "barrel_percent": 4.5, "xslg": 0.360, "hard_hit_percent": 31.0}))
    high = analyze_batter(make_batter(season={"iso": 0.270, "barrel_percent": 15.0, "xslg": 0.540, "hard_hit_percent": 48.0}))
    assert high.power_score > low.power_score


def test_lower_k_percent_increases_contact_score():
    high_k = analyze_batter(make_batter(season={"k_percent": 30.0}, recent={"k_percent": 30.0}))
    low_k = analyze_batter(make_batter(season={"k_percent": 14.0}, recent={"k_percent": 14.0}))
    assert low_k.contact_score > high_k.contact_score


def test_easier_pitcher_matchup_increases_matchup_score():
    tough = analyze_batter(make_batter(opposing_pitcher={"k_percent": 32.0, "xwoba_allowed": 0.285, "hard_hit_percent_allowed": 31.0}))
    easy = analyze_batter(make_batter(opposing_pitcher={"k_percent": 14.0, "xwoba_allowed": 0.355, "hard_hit_percent_allowed": 48.0}))
    assert easy.matchup_score > tough.matchup_score


def test_lineup_position_score_favors_top_of_order():
    leadoff = analyze_batter(make_batter(batting_order=1))
    bottom = analyze_batter(make_batter(batting_order=9))
    assert leadoff.lineup_position_score > bottom.lineup_position_score


def test_lineup_position_does_not_overwhelm_skill():
    """A clearly superior hitter batting 9th should still outscore a weak
    hitter batting 1st overall -- batting order is one input, not the
    whole story."""
    elite_bottom = analyze_batter(make_batter(
        batting_order=9,
        season={"iso": 0.280, "barrel_percent": 16.0, "hard_hit_percent": 50.0, "xwoba": 0.400, "k_percent": 15.0},
    ))
    weak_leadoff = analyze_batter(make_batter(
        batting_order=1,
        season={"iso": 0.090, "barrel_percent": 3.0, "hard_hit_percent": 28.0, "xwoba": 0.270, "k_percent": 30.0},
    ))
    assert elite_bottom.overall_score > weak_leadoff.overall_score


# ----------------------------------------------------------------------------
# Risk / confidence
# ----------------------------------------------------------------------------


def test_high_k_percent_increases_risk():
    low = analyze_batter(make_batter(season={"k_percent": 14.0}, recent={"k_percent": 14.0}))
    high = analyze_batter(make_batter(season={"k_percent": 33.0}, recent={"k_percent": 33.0}))
    assert high.risk_score > low.risk_score


def test_larger_sample_improves_confidence():
    small = analyze_batter(make_batter(season={"plate_appearances": 40}, recent={"plate_appearances": 5}))
    large = analyze_batter(make_batter(season={"plate_appearances": 450}, recent={"plate_appearances": 55}))
    assert large.confidence > small.confidence


def test_missing_critical_data_lowers_confidence():
    full = analyze_batter(make_batter())
    empty = analyze_batter(BatterInput(player_id="EMPTY", name="Empty", team="AAA", opponent="BBB"))
    assert empty.confidence < full.confidence


def test_missing_salary_does_not_meaningfully_reduce_confidence():
    with_salary = analyze_batter(make_batter(salary=5000))
    without_salary = analyze_batter(make_batter(salary=None))
    assert with_salary.confidence == without_salary.confidence


def test_poor_lineup_slot_increases_risk():
    top = analyze_batter(make_batter(batting_order=2))
    bottom = analyze_batter(make_batter(batting_order=9))
    assert bottom.risk_score > top.risk_score


def test_tiny_sample_increases_risk():
    established = analyze_batter(make_batter(season={"plate_appearances": 400}))
    rookie = analyze_batter(make_batter(season={"plate_appearances": 35}))
    assert rookie.risk_score > established.risk_score


# ----------------------------------------------------------------------------
# Tags
# ----------------------------------------------------------------------------


def test_elite_power_tags():
    entry = analyze_batter(make_batter(season={"iso": 0.260, "barrel_percent": 14.0, "hard_hit_percent": 47.0, "xwoba": 0.380}))
    assert "elite_power" in entry.tags
    assert "elite_barrel" in entry.tags
    assert "elite_hard_hit" in entry.tags
    assert "elite_xwoba" in entry.tags


def test_low_strikeout_and_walk_upside_tags():
    entry = analyze_batter(make_batter(season={"k_percent": 12.0, "bb_percent": 14.0}, recent={"k_percent": 12.0, "bb_percent": 14.0}))
    assert "low_strikeout" in entry.tags
    assert "walk_upside" in entry.tags


def test_lineup_order_tags():
    leadoff = analyze_batter(make_batter(batting_order=1))
    cleanup = analyze_batter(make_batter(batting_order=4))
    bottom = analyze_batter(make_batter(batting_order=8))
    assert "leadoff" in leadoff.tags and "top_order" in leadoff.tags
    assert "cleanup_hitter" in cleanup.tags
    assert "bottom_order" in bottom.tags
    assert "top_order" not in bottom.tags


def test_high_k_risk_tag():
    entry = analyze_batter(make_batter(season={"k_percent": 32.0}, recent={"k_percent": 32.0}))
    assert "high_k_risk" in entry.tags


def test_tough_and_strong_pitcher_matchup_tags():
    tough = analyze_batter(make_batter(opposing_pitcher={"k_percent": 33.0, "xwoba_allowed": 0.282, "hard_hit_percent_allowed": 30.0}))
    strong = analyze_batter(make_batter(opposing_pitcher={"k_percent": 13.0, "xwoba_allowed": 0.358, "hard_hit_percent_allowed": 49.0}))
    assert "tough_pitcher_matchup" in tough.tags
    assert "strong_pitcher_matchup" in strong.tags


def test_positive_and_negative_contact_trend_tags():
    positive = analyze_batter(make_batter(trends={
        "exit_velocity_trend": 2.0, "hard_hit_trend": 6.0, "barrel_trend": 3.0, "xwoba_trend": 0.03, "strikeout_rate_trend": 4.0,
    }))
    negative = analyze_batter(make_batter(trends={
        "exit_velocity_trend": -2.0, "hard_hit_trend": -6.0, "barrel_trend": -3.0, "xwoba_trend": -0.03, "strikeout_rate_trend": -4.0,
    }))
    assert "positive_contact_trend" in positive.tags
    assert "negative_contact_trend" in negative.tags


def test_platoon_advantage_and_disadvantage_tags():
    advantage = analyze_batter(make_batter(
        season={"xwoba": 0.320},
        opposing_pitcher={"throwing_hand": "R"},
        vs_rhp={"woba": 0.370},
    ))
    disadvantage = analyze_batter(make_batter(
        season={"xwoba": 0.340},
        opposing_pitcher={"throwing_hand": "L"},
        vs_lhp={"woba": 0.290},
    ))
    assert "platoon_advantage" in advantage.tags
    assert "platoon_disadvantage" in disadvantage.tags


# ----------------------------------------------------------------------------
# Backward-compat / robustness
# ----------------------------------------------------------------------------


def test_missing_optional_data_does_not_crash():
    sparse = BatterInput(player_id="SPARSE", name="Sparse Hitter", team="AAA", opponent="BBB", batting_order=6)
    entry = analyze_batter(sparse)
    assert entry.projection >= 0.0
    assert 0.0 <= entry.confidence <= 100.0
    assert 0.0 <= entry.risk_score <= 100.0


def test_no_opposing_pitcher_data_does_not_crash():
    b = BatterInput(player_id="1", name="X", team="AAA", opponent="BBB", batting_order=1, season=SeasonBattingStats(**BASE_SEASON))
    entry = analyze_batter(b)
    assert entry.matchup_score == 50.0  # fully neutral, no data at all


def test_zero_plate_appearances_season_does_not_crash():
    b = make_batter(season={"plate_appearances": 0, "hits": 0, "doubles": 0, "triples": 0, "home_runs": 0, "at_bats": 0})
    entry = analyze_batter(b)
    assert entry.projection >= 0.0


# ----------------------------------------------------------------------------
# Ranking
# ----------------------------------------------------------------------------


def test_rankings_are_deterministic():
    batters = [make_batter(player_id=f"P{i}", season={"iso": 0.100 + i * 0.01}) for i in range(8)]
    board1 = [e.player_id for e in analyze_slate(batters)]
    board2 = [e.player_id for e in analyze_slate(batters)]
    assert board1 == board2


def test_slate_ranked_by_overall_score_descending():
    batters = [make_batter(player_id=f"P{i}", season={"iso": 0.100 + i * 0.02, "barrel_percent": 4.0 + i}) for i in range(6)]
    board = analyze_slate(batters)
    for a, b in zip(board, board[1:]):
        assert a.overall_score >= b.overall_score


def test_higher_salary_does_not_automatically_increase_overall_score():
    cheap_elite = make_batter(player_id="CHEAP", salary=3000, season={"iso": 0.270, "barrel_percent": 15.0, "hard_hit_percent": 49.0, "xwoba": 0.390, "k_percent": 14.0})
    expensive_weak = make_batter(player_id="EXPENSIVE", salary=6500, season={"iso": 0.100, "barrel_percent": 3.5, "hard_hit_percent": 29.0, "xwoba": 0.270, "k_percent": 30.0})
    cheap_entry = analyze_batter(cheap_elite)
    expensive_entry = analyze_batter(expensive_weak)
    assert cheap_entry.overall_score > expensive_entry.overall_score
