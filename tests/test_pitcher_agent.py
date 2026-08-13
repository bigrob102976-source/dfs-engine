from agents.pitcher_agent import analyze_pitcher, analyze_slate
from models.pitcher import (
    Availability,
    GameContext,
    OpponentStats,
    PitcherInput,
    RecentStats,
    SeasonStats,
    TrendMetrics,
)
from services.pitcher_data import DEFAULT_SAMPLE_PATH, load_pitchers_from_json

# A fully-populated baseline pitcher. Individual tests override just the
# section(s) relevant to what they're checking, so unrelated sub-scores
# stay constant between the two pitchers being compared.

BASE_SEASON = dict(
    innings=100.0, era=3.80, fip=3.80, xfip=3.80, siera=3.80,
    k_percent=24.0, bb_percent=8.0, k_minus_bb_percent=16.0,
    swinging_strike_percent=11.0, csw_percent=28.0,
    ground_ball_percent=44.0, hard_hit_percent=35.0, barrel_percent=7.0,
    xera=3.80, xwoba_allowed=0.310,
)
BASE_RECENT = dict(
    innings=15.0, k_percent=24.0, bb_percent=8.0,
    velocity=93.5, season_velocity=93.5, pitch_count_average=90.0,
)
BASE_OPPONENT = dict(
    team="BBB", strikeout_percent_vs_hand=22.0, woba_vs_hand=0.310,
    iso_vs_hand=0.150, implied_runs=4.2,
)
BASE_GAME = dict(park_factor=100.0, weather_pitching_factor=100.0, umpire_pitching_factor=100.0)
BASE_AVAILABILITY = dict(confirmed_starter=True, expected_pitch_count=92.0)
BASE_TRENDS = dict()  # all None by default -- most tests don't care about trends


def make_pitcher(season=None, recent=None, opponent=None, game=None, availability=None, trends=None, **top):
    defaults = dict(player_id="TEST1", name="Test Pitcher", team="AAA", opponent="BBB", salary=8000, throwing_hand="R")
    defaults.update(top)
    return PitcherInput(
        **defaults,
        season=SeasonStats(**{**BASE_SEASON, **(season or {})}),
        recent=RecentStats(**{**BASE_RECENT, **(recent or {})}),
        opponent_stats=OpponentStats(**{**BASE_OPPONENT, **(opponent or {})}),
        game=GameContext(**{**BASE_GAME, **(game or {})}),
        availability=Availability(**{**BASE_AVAILABILITY, **(availability or {})}),
        trends=TrendMetrics(**{**BASE_TRENDS, **(trends or {})}),
    )


def test_higher_k_percent_increases_strikeout_score():
    low = analyze_pitcher(make_pitcher(season={"k_percent": 18.0}, recent={"k_percent": 18.0}))
    high = analyze_pitcher(make_pitcher(season={"k_percent": 32.0}, recent={"k_percent": 32.0}))
    assert high.strikeout_score > low.strikeout_score


def test_higher_opponent_strikeout_rate_improves_matchup():
    low = analyze_pitcher(make_pitcher(opponent={"strikeout_percent_vs_hand": 16.0}))
    high = analyze_pitcher(make_pitcher(opponent={"strikeout_percent_vs_hand": 29.0}))
    assert high.matchup_score > low.matchup_score


def test_higher_opponent_implied_runs_hurts_matchup_and_run_prevention():
    low = analyze_pitcher(make_pitcher(opponent={"implied_runs": 3.2}))
    high = analyze_pitcher(make_pitcher(opponent={"implied_runs": 5.4}))
    assert high.matchup_score < low.matchup_score
    assert high.run_prevention_score < low.run_prevention_score


def test_higher_barrel_rate_increases_risk_and_tags():
    low = analyze_pitcher(make_pitcher(season={"barrel_percent": 4.0}))
    high = analyze_pitcher(make_pitcher(season={"barrel_percent": 13.0}))
    assert high.risk_score > low.risk_score
    assert "high_barrel_risk" in high.tags
    assert "high_barrel_risk" not in low.tags


def test_lower_expected_pitch_count_increases_risk():
    low = analyze_pitcher(make_pitcher(availability={"expected_pitch_count": 100.0}))
    high = analyze_pitcher(make_pitcher(availability={"expected_pitch_count": 68.0}))
    assert high.risk_score > low.risk_score


def test_velocity_decline_creates_warning_tag_and_risk():
    stable = analyze_pitcher(make_pitcher(recent={"velocity": 93.5, "season_velocity": 93.5}))
    declined = analyze_pitcher(make_pitcher(recent={"velocity": 91.5, "season_velocity": 94.0}))
    assert "velocity_down" in declined.tags
    assert "velocity_down" not in stable.tags
    assert declined.risk_score > stable.risk_score


def test_missing_optional_data_does_not_crash():
    sparse = PitcherInput(
        player_id="SPARSE1",
        name="Sparse Pitcher",
        team="AAA",
        opponent="BBB",
        salary=5000,
        season=SeasonStats(k_percent=20.0, bb_percent=9.0),
    )
    entry = analyze_pitcher(sparse)
    assert entry.projection >= 0.0
    assert 0.0 <= entry.confidence <= 100.0
    assert 0.0 <= entry.risk_score <= 100.0


def test_missing_critical_data_lowers_confidence():
    full = analyze_pitcher(make_pitcher())
    empty = analyze_pitcher(PitcherInput(player_id="EMPTY1", name="Empty", team="AAA", opponent="BBB", salary=5000))
    assert empty.confidence < full.confidence


def test_higher_salary_does_not_automatically_increase_overall_score():
    cheap_elite = make_pitcher(
        player_id="CHEAP", salary=4000,
        season={"k_percent": 33.0, "siera": 2.80, "xfip": 2.85, "fip": 2.90, "bb_percent": 5.0},
        recent={"k_percent": 33.0, "bb_percent": 5.0},
    )
    expensive_mediocre = make_pitcher(
        player_id="EXPENSIVE", salary=11000,
        season={"k_percent": 17.0, "siera": 4.80, "xfip": 4.70, "fip": 4.60, "bb_percent": 10.0},
        recent={"k_percent": 17.0, "bb_percent": 10.0},
    )
    cheap_entry = analyze_pitcher(cheap_elite)
    expensive_entry = analyze_pitcher(expensive_mediocre)
    assert cheap_entry.salary < expensive_entry.salary
    assert cheap_entry.overall_score > expensive_entry.overall_score


def test_rankings_are_deterministic():
    pitchers = load_pitchers_from_json(DEFAULT_SAMPLE_PATH)
    board1 = [e.player_id for e in analyze_slate(pitchers)]
    board2 = [e.player_id for e in analyze_slate(pitchers)]
    assert board1 == board2


def test_sample_slate_loads_and_scores_without_crashing():
    pitchers = load_pitchers_from_json(DEFAULT_SAMPLE_PATH)
    assert len(pitchers) >= 6
    board = analyze_slate(pitchers)
    assert len(board) == len(pitchers)
    # Ranked strictly by overall_score (descending, ties broken deterministically).
    for a, b in zip(board, board[1:]):
        assert a.overall_score >= b.overall_score


# ----------------------------------------------------------------------------
# Milestone 5: Statcast-driven scoring enhancements
# ----------------------------------------------------------------------------


def test_elite_csw_improves_strikeout_score_and_tags():
    low = analyze_pitcher(make_pitcher(season={"csw_percent": 25.0}))
    high = analyze_pitcher(make_pitcher(season={"csw_percent": 32.0}))
    assert high.strikeout_score > low.strikeout_score
    assert "elite_csw" in high.tags
    assert "elite_csw" not in low.tags


def test_velocity_increase_improves_strikeout_score():
    flat = analyze_pitcher(make_pitcher(recent={"velocity": 94.0, "season_velocity": 94.0}))
    up = analyze_pitcher(make_pitcher(recent={"velocity": 95.8, "season_velocity": 94.0}))
    assert up.strikeout_score > flat.strikeout_score
    assert "velocity_up" in up.tags


def test_declining_csw_trend_increases_risk():
    stable = analyze_pitcher(make_pitcher(trends={"csw_trend": 0.0}))
    declining = analyze_pitcher(make_pitcher(trends={"csw_trend": -4.0}))
    assert declining.risk_score > stable.risk_score


def test_high_hard_hit_rate_increases_risk_and_hurts_run_prevention():
    low = analyze_pitcher(make_pitcher(season={"hard_hit_percent": 30.0}))
    high = analyze_pitcher(make_pitcher(season={"hard_hit_percent": 48.0}))
    assert high.risk_score > low.risk_score
    assert high.run_prevention_score < low.run_prevention_score


def test_elite_contact_suppression_tag():
    suppressed = analyze_pitcher(make_pitcher(season={"hard_hit_percent": 31.0, "barrel_percent": 3.5}))
    normal = analyze_pitcher(make_pitcher(season={"hard_hit_percent": 40.0, "barrel_percent": 9.0}))
    assert "elite_contact_suppression" in suppressed.tags
    assert "elite_contact_suppression" not in normal.tags


def test_ground_ball_specialist_tag():
    specialist = analyze_pitcher(make_pitcher(season={"ground_ball_percent": 55.0}))
    flyball = analyze_pitcher(make_pitcher(season={"ground_ball_percent": 36.0}))
    assert "ground_ball_specialist" in specialist.tags
    assert "ground_ball_specialist" not in flyball.tags


def test_xera_regression_tags_both_directions():
    unlucky = analyze_pitcher(make_pitcher(season={"era": 5.20, "xera": 3.60}))  # ERA much worse than xERA
    lucky = analyze_pitcher(make_pitcher(season={"era": 2.50, "xera": 4.20}))    # ERA much better than xERA
    assert "xERA_positive_regression" in unlucky.tags
    assert "xERA_negative_regression" in lucky.tags


def test_positive_and_negative_trend_tags():
    positive = analyze_pitcher(make_pitcher(trends={
        "velocity_trend": 1.0, "swinging_strike_trend": 2.0, "hard_hit_trend": 3.0, "barrel_trend": 1.5, "ground_ball_trend": 2.0,
    }))
    negative = analyze_pitcher(make_pitcher(trends={
        "velocity_trend": -1.0, "swinging_strike_trend": -2.0, "hard_hit_trend": -3.0, "barrel_trend": -1.5, "ground_ball_trend": -2.0,
    }))
    assert "positive_trend" in positive.tags
    assert "negative_trend" in negative.tags


def test_backward_compatible_pitcher_without_any_milestone5_fields():
    """A PitcherInput built exactly the way Milestone 2/4 code built one --
    no trends, no xba/exit-velocity/pitch_mix, no recent Statcast fields --
    must still score correctly. Scores are NOT expected to numerically
    match pre-Milestone-5 output (the composite weights were deliberately
    rebalanced to make room for new signals), only to remain directionally
    sane and crash-free with every new field absent."""
    old_style_low = PitcherInput(
        player_id="OLD1", name="Old Style Low", team="AAA", opponent="BBB", salary=7000,
        season=SeasonStats(era=4.00, k_percent=18.0, bb_percent=8.0, k_minus_bb_percent=10.0),
        recent=RecentStats(innings=15.0, k_percent=18.0, bb_percent=8.0, pitch_count_average=90.0),
        opponent_stats=OpponentStats(strikeout_percent_vs_hand=20.0, implied_runs=4.2),
        availability=Availability(expected_pitch_count=90.0),
    )
    old_style_high = PitcherInput(
        player_id="OLD2", name="Old Style High", team="AAA", opponent="BBB", salary=7000,
        season=SeasonStats(era=3.00, k_percent=32.0, bb_percent=6.0, k_minus_bb_percent=26.0),
        recent=RecentStats(innings=15.0, k_percent=32.0, bb_percent=6.0, pitch_count_average=90.0),
        opponent_stats=OpponentStats(strikeout_percent_vs_hand=20.0, implied_runs=4.2),
        availability=Availability(expected_pitch_count=90.0),
    )
    low_entry = analyze_pitcher(old_style_low)
    high_entry = analyze_pitcher(old_style_high)

    assert high_entry.strikeout_score > low_entry.strikeout_score
    assert high_entry.overall_score > low_entry.overall_score
    assert 0.0 <= low_entry.confidence <= 100.0
    assert 0.0 <= high_entry.risk_score <= 100.0


def test_slate_relative_csw_reason_appears_for_top_pitcher_on_large_slate():
    pitchers = [
        make_pitcher(player_id=f"P{i}", season={"csw_percent": 24.0 + i}) for i in range(6)
    ]
    board = analyze_slate(pitchers)
    top = next(e for e in board if e.player_id == "P5")  # csw_percent=29.0, the highest
    assert any("ranks 1 of" in r for r in top.reasons)


def test_slate_relative_csw_reason_absent_on_small_slate():
    pitchers = [make_pitcher(player_id=f"P{i}", season={"csw_percent": 24.0 + i}) for i in range(2)]
    board = analyze_slate(pitchers)
    assert all("ranks" not in r for e in board for r in e.reasons)
