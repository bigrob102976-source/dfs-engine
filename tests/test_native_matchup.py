from config import native_projection_config as cfg
from config.projection_engine_config import BULLPEN_STRENGTH_ELITE, BULLPEN_STRENGTH_WEAK
from models.batter import BatterInput, OpposingPitcherContext, PlatoonSplitStats, SeasonBattingStats
from models.pitcher import PitcherInput, SeasonStats

from native_projections.matchup import (
    OpposingLineupQuality,
    build_opposing_lineup_index,
    environment_adjustment,
    hitter_matchup_adjustment,
    pitcher_matchup_adjustment,
)


def make_batter(season=None, opposing_pitcher=None, vs_rhp=None, vs_lhp=None, **top):
    defaults = dict(player_id="B1", name="Test Hitter", team="AAA", opponent="BBB", batting_order=3)
    defaults.update(top)
    return BatterInput(
        **defaults,
        season=SeasonBattingStats(**(season or {})),
        opposing_pitcher=OpposingPitcherContext(**(opposing_pitcher or {})),
        vs_rhp=PlatoonSplitStats(**(vs_rhp or {})),
        vs_lhp=PlatoonSplitStats(**(vs_lhp or {})),
    )


def make_pitcher(**top):
    defaults = dict(player_id="P1", name="Test Pitcher", team="AAA", opponent="BBB")
    defaults.update(top)
    return PitcherInput(**defaults, season=SeasonStats())


# ----------------------------------------------------------------------------
# Hitter vs. opposing pitcher
# ----------------------------------------------------------------------------


def test_no_opposing_pitcher_context_gives_zero_adjustment():
    b = make_batter()
    result = hitter_matchup_adjustment(b)
    assert result.points == 0.0
    assert "no opposing pitcher context" in result.reasons[0].lower()


def test_weak_opposing_pitcher_gives_positive_adjustment():
    b = make_batter(
        opposing_pitcher=dict(player_id="OPP1", k_percent=14.0, xwoba_allowed=0.355, hard_hit_percent_allowed=48.0)
    )
    result = hitter_matchup_adjustment(b)
    assert result.points > 0


def test_elite_opposing_pitcher_gives_negative_adjustment():
    b = make_batter(
        opposing_pitcher=dict(player_id="OPP1", k_percent=33.0, xwoba_allowed=0.285, hard_hit_percent_allowed=31.0)
    )
    result = hitter_matchup_adjustment(b)
    assert result.points < 0


def test_platoon_split_shifts_adjustment_when_present():
    base = make_batter(opposing_pitcher=dict(player_id="OPP1", throwing_hand="L", k_percent=22.0))
    strong_platoon = make_batter(
        opposing_pitcher=dict(player_id="OPP1", throwing_hand="L", k_percent=22.0),
        vs_lhp=dict(woba=0.400),
    )
    weak_platoon = make_batter(
        opposing_pitcher=dict(player_id="OPP1", throwing_hand="L", k_percent=22.0),
        vs_lhp=dict(woba=0.280),
    )
    base_points = hitter_matchup_adjustment(base).points
    strong_points = hitter_matchup_adjustment(strong_platoon).points
    weak_points = hitter_matchup_adjustment(weak_platoon).points
    assert strong_points > base_points > weak_points


def test_matchup_points_capped_at_configured_max():
    b = make_batter(
        opposing_pitcher=dict(player_id="OPP1", k_percent=1.0, xwoba_allowed=1.0, hard_hit_percent_allowed=100.0)
    )
    result = hitter_matchup_adjustment(b)
    assert result.points <= cfg.MATCHUP_HITTER_MAX_POINTS + 1e-6


# ----------------------------------------------------------------------------
# Opposing lineup index / pitcher-vs-lineup
# ----------------------------------------------------------------------------


def test_build_opposing_lineup_index_only_counts_confirmed_hitters():
    hitters = [
        make_batter(player_id="H1", team="CCC", batting_order=1, season=dict(k_percent=20.0)),
        make_batter(player_id="H2", team="CCC", batting_order=2, season=dict(k_percent=22.0)),
        make_batter(player_id="H3", team="CCC", batting_order=None, season=dict(k_percent=50.0)),  # unconfirmed, excluded
    ]
    index = build_opposing_lineup_index(hitters)
    assert index["CCC"].hitters_count == 2
    assert abs(index["CCC"].avg_k_percent - 21.0) < 1e-9


def test_opposing_lineup_index_flags_partial_below_minimum():
    hitters = [make_batter(player_id="H1", team="CCC", batting_order=1)]
    index = build_opposing_lineup_index(hitters)
    assert index["CCC"].is_partial is True


def test_pitcher_matchup_none_lineup_gives_zero():
    p = make_pitcher()
    result = pitcher_matchup_adjustment(p, None)
    assert result.points == 0.0


def test_pitcher_matchup_partial_lineup_gives_zero_with_reason():
    p = make_pitcher()
    partial = OpposingLineupQuality(team="CCC", hitters_count=2, avg_k_percent=20.0, avg_bb_percent=8.0, avg_iso=0.150, avg_woba=0.320, is_partial=True)
    result = pitcher_matchup_adjustment(p, partial)
    assert result.points == 0.0
    assert "confirmed opposing hitters" in result.reasons[0].lower()


def test_pitcher_matchup_weak_lineup_gives_positive_adjustment():
    p = make_pitcher()
    weak_lineup = OpposingLineupQuality(team="CCC", hitters_count=6, avg_k_percent=29.0, avg_bb_percent=7.0, avg_iso=0.130, avg_woba=0.290, is_partial=False)
    result = pitcher_matchup_adjustment(p, weak_lineup)
    assert result.points > 0


def test_pitcher_matchup_strong_lineup_gives_negative_adjustment():
    p = make_pitcher()
    strong_lineup = OpposingLineupQuality(team="CCC", hitters_count=6, avg_k_percent=16.0, avg_bb_percent=9.0, avg_iso=0.210, avg_woba=0.355, is_partial=False)
    result = pitcher_matchup_adjustment(p, strong_lineup)
    assert result.points < 0


# ----------------------------------------------------------------------------
# Environment adjustment
# ----------------------------------------------------------------------------


def test_no_environment_data_gives_zero_with_reason():
    result = environment_adjustment("hitter")
    assert result.points == 0.0
    assert "no environment data" in result.reasons[0].lower()


def test_park_factor_above_neutral_helps_hitters_and_hurts_pitchers():
    hitter_result = environment_adjustment("hitter", park_factor=115.0)
    pitcher_result = environment_adjustment("pitcher", park_factor=115.0)
    assert hitter_result.points > 0
    assert pitcher_result.points < 0


def test_mock_vegas_contributes_zero_points_never_influences_real_projection():
    # Milestone 24: mock Vegas data must NEVER influence a real/live
    # projection -- not merely "capped small" as in the pre-M24 design.
    mock_result = environment_adjustment("hitter", team_implied_runs=5.5, vegas_is_mock=True)
    assert mock_result.points == 0.0
    assert "never influences" in mock_result.reasons[0].lower()


def test_real_vegas_contributes_nonzero_points():
    real_result = environment_adjustment("hitter", team_implied_runs=5.5, vegas_is_mock=False)
    assert real_result.points != 0.0


def test_weather_favoring_hitter_gives_positive_points():
    result = environment_adjustment("hitter", weather_favors=["hitter", "hitter", "neutral"])
    assert result.points > 0


def test_weather_favoring_pitcher_gives_negative_points_for_hitter():
    result = environment_adjustment("hitter", weather_favors=["pitcher", "pitcher"])
    assert result.points < 0


def test_bullpen_adjustment_only_applies_to_hitters():
    hitter_result = environment_adjustment("hitter", opposing_bullpen_strength=BULLPEN_STRENGTH_WEAK)
    pitcher_result = environment_adjustment("pitcher", opposing_bullpen_strength=BULLPEN_STRENGTH_WEAK)
    assert hitter_result.points != 0.0
    assert pitcher_result.points == 0.0


def test_weak_opposing_bullpen_helps_hitter_more_than_elite_bullpen():
    weak = environment_adjustment("hitter", opposing_bullpen_strength=BULLPEN_STRENGTH_WEAK)
    elite = environment_adjustment("hitter", opposing_bullpen_strength=BULLPEN_STRENGTH_ELITE)
    assert weak.points > elite.points
