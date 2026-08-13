import pytest

from models.batter import BatterInput
from research.statcast_batter_collector import RawBatterStatcastData
from research.statcast_batter_enrichment import (
    apply_statcast_to_batter_inputs,
    compute_trends,
    index_season_leaderboards,
    parse_recent_batter_statcast,
    parse_season_batter_statcast,
)

RETRIEVED_AT = "2026-08-11T12:00:00+00:00"


def _pitch(pitch_type, description=None, launch_speed=None, launch_angle=None, bb_type=None,
           launch_speed_angle=None, woba_value=None, estimated_woba_using_speedangle=None):
    return {
        "pitch_type": pitch_type, "description": description or "ball",
        "launch_speed": launch_speed, "launch_angle": launch_angle, "bb_type": bb_type,
        "launch_speed_angle": launch_speed_angle, "woba_value": woba_value,
        "estimated_woba_using_speedangle": estimated_woba_using_speedangle,
    }


# 6 pitches: 3 PA-ending batted balls (2 FF, 1 SL), 3 non-PA-ending pitches.
# Hand-verified: in_play=3, EVs=[95.0,100.0,80.0]->mean 91.7, max 100.0,
#   hard_hit (>=95): 2/3=66.7%, barrel(lsa=='6'): 1/3=33.3%
_RECENT_ROWS = [
    _pitch("FF", "ball"),
    _pitch("SL", "swinging_strike"),
    _pitch("FF", "hit_into_play", launch_speed="95.0", launch_angle="20", bb_type="fly_ball", launch_speed_angle="6", woba_value="1.0", estimated_woba_using_speedangle="0.900"),
    _pitch("FF", "hit_into_play", launch_speed="100.0", launch_angle="15", bb_type="line_drive", launch_speed_angle="4", woba_value="1.25", estimated_woba_using_speedangle="1.100"),
    _pitch("SL", "hit_into_play", launch_speed="80.0", launch_angle="5", bb_type="ground_ball", launch_speed_angle="1", woba_value="0.0", estimated_woba_using_speedangle="0.050"),
    _pitch("CU", "foul"),
]


def test_parse_recent_batter_statcast_exit_velocity_and_max():
    line = parse_recent_batter_statcast(_RECENT_ROWS, "1", "2026", RETRIEVED_AT)
    assert line.exit_velocity == pytest.approx(91.7, abs=0.1)
    assert line.max_exit_velocity == 100.0


def test_parse_recent_batter_statcast_hard_hit_and_barrel_percent():
    line = parse_recent_batter_statcast(_RECENT_ROWS, "1", "2026", RETRIEVED_AT)
    assert line.hard_hit_percent == pytest.approx(66.7, abs=0.1)  # 2 of 3 batted balls >= 95mph
    assert line.barrel_percent == pytest.approx(33.3, abs=0.1)    # only launch_speed_angle == "6"


def test_parse_recent_batter_statcast_xwoba_averages_pa_ending_events_only():
    line = parse_recent_batter_statcast(_RECENT_ROWS, "1", "2026", RETRIEVED_AT)
    # 4 PA-ending rows have woba_value set (swinging_strike + 3 batted balls);
    # estimated_woba_using_speedangle only on the 3 batted-ball rows here since
    # the whiff has none in this fixture.
    assert line.xwoba == pytest.approx((0.900 + 1.100 + 0.050) / 3, abs=0.001)


def test_parse_recent_batter_statcast_pitch_type_performance_requires_min_sample():
    # FF has 2 PA-ending events (below MIN_PITCH_TYPE_SAMPLE=3) -> excluded.
    # SL has 2 PA-ending events -> also excluded. Neither should appear.
    line = parse_recent_batter_statcast(_RECENT_ROWS, "1", "2026", RETRIEVED_AT)
    assert line.pitch_type_performance is None


def test_parse_recent_batter_statcast_pitch_type_performance_included_with_enough_sample():
    rows = _RECENT_ROWS + [
        _pitch("FF", "hit_into_play", launch_speed="90.0", bb_type="ground_ball", woba_value="0.5"),
    ]
    line = parse_recent_batter_statcast(rows, "1", "2026", RETRIEVED_AT)
    assert line.pitch_type_performance is not None
    assert "FF" in line.pitch_type_performance  # now has 3 PA-ending FF events


@pytest.mark.parametrize("rows", [None, []])
def test_parse_recent_batter_statcast_handles_missing_data(rows):
    assert parse_recent_batter_statcast(rows, "1", "2026", RETRIEVED_AT) is None


def test_parse_recent_batter_statcast_zero_balls_in_play_is_safe():
    only_takes = [_pitch("FF", "ball"), _pitch("SL", "called_strike")]
    line = parse_recent_batter_statcast(only_takes, "1", "2026", RETRIEVED_AT)
    assert line.exit_velocity is None
    assert line.hard_hit_percent is None
    assert line.barrel_percent is None


# ----------------------------------------------------------------------------
# Season parsing
# ----------------------------------------------------------------------------


def _season_index(**overrides):
    expected = [{"player_id": "1", "est_ba": ".270", "est_slg": ".460", "est_woba": ".350", "woba": ".345"}]
    custom = [{
        "player_id": "1", "pa": "400", "hard_hit_percent": "42.0", "barrel_batted_rate": "9.5",
        "exit_velocity_avg": "90.0", "launch_angle_avg": "13.0", "sweet_spot_percent": "35.0", "avg_swing_speed": "72.5",
    }]
    raw = RawBatterStatcastData(
        date="2026-08-11", season="2026",
        expected_statistics=overrides.get("expected", expected),
        custom_leaderboard=overrides.get("custom", custom),
    )
    return index_season_leaderboards(raw)


def test_parse_season_batter_statcast_xba_xslg_xwoba_woba():
    line = parse_season_batter_statcast(_season_index(), "1", "2026", RETRIEVED_AT)
    assert line.xba == 0.270
    assert line.xslg == 0.460
    assert line.xwoba == 0.350
    assert line.woba == 0.345  # Savant's REAL wOBA, not an approximation


def test_parse_season_batter_statcast_hard_hit_barrel_exit_velocity_bat_speed():
    line = parse_season_batter_statcast(_season_index(), "1", "2026", RETRIEVED_AT)
    assert line.hard_hit_percent == 42.0
    assert line.barrel_percent == 9.5
    assert line.exit_velocity == 90.0
    assert line.bat_speed == 72.5  # avg_swing_speed


def test_parse_season_batter_statcast_returns_none_for_unknown_player():
    assert parse_season_batter_statcast(_season_index(), "999", "2026", RETRIEVED_AT) is None


def test_parse_season_batter_statcast_partial_availability():
    idx = _season_index(expected=[])
    line = parse_season_batter_statcast(idx, "1", "2026", RETRIEVED_AT)
    assert line is not None
    assert line.xba is None
    assert line.hard_hit_percent == 42.0  # unaffected


# ----------------------------------------------------------------------------
# Trends
# ----------------------------------------------------------------------------


def test_compute_trends_signs_and_inversion():
    season = parse_season_batter_statcast(_season_index(), "1", "2026", RETRIEVED_AT)
    recent = parse_recent_batter_statcast(_RECENT_ROWS, "1", "2026", RETRIEVED_AT)
    # season k%=25, recent k%=15 -> fewer Ks recently -> positive (favorable) strikeout_rate_trend
    trends = compute_trends(season, recent, season_k_percent=25.0, recent_k_percent=15.0, season_bb_percent=8.0, recent_bb_percent=12.0)
    assert trends["strikeout_rate_trend"] == pytest.approx(10.0)
    assert trends["walk_rate_trend"] == pytest.approx(4.0)  # recent bb% higher -> favorable, NOT inverted
    assert trends["exit_velocity_trend"] is not None


def test_compute_trends_missing_side_gives_none():
    season = parse_season_batter_statcast(_season_index(), "1", "2026", RETRIEVED_AT)
    trends = compute_trends(season, None, 25.0, None, 8.0, None)
    assert trends["exit_velocity_trend"] is None
    assert trends["strikeout_rate_trend"] is None


# ----------------------------------------------------------------------------
# Merge into BatterInput
# ----------------------------------------------------------------------------


def test_apply_statcast_merges_and_computes_trends_using_mlb_stats_k_percent():
    from models.batter import SeasonBattingStats, RecentBattingStats

    raw = RawBatterStatcastData(
        date="2026-08-11", season="2026",
        expected_statistics=[{"player_id": "1", "est_ba": ".270", "est_slg": ".460", "est_woba": ".350", "woba": ".345"}],
        custom_leaderboard=[{"player_id": "1", "pa": "400", "hard_hit_percent": "42.0", "barrel_batted_rate": "9.5", "exit_velocity_avg": "90.0"}],
        recent_pitch_level={"1": _RECENT_ROWS},
    )
    # Simulate that MLB-stats enrichment already ran (season/recent k% present).
    p = BatterInput(
        player_id="1", name="Test", team="AAA", opponent="BBB",
        season=SeasonBattingStats(k_percent=25.0, bb_percent=8.0),
        recent=RecentBattingStats(k_percent=15.0, bb_percent=12.0),
    )
    enriched, provenance = apply_statcast_to_batter_inputs([p], raw, RETRIEVED_AT)

    e = enriched[0]
    assert e.season.xwoba == 0.350
    assert e.recent.exit_velocity is not None
    assert e.trends.strikeout_rate_trend == pytest.approx(10.0)
    types = {r["type"] for r in provenance}
    assert types == {"season_batter_statcast", "recent_batter_statcast", "batter_trends"}


def test_apply_statcast_leaves_batter_unenriched_when_no_data():
    raw = RawBatterStatcastData(date="2026-08-11", season="2026")
    p = BatterInput(player_id="2", name="Nobody", team="AAA", opponent="BBB")
    enriched, provenance = apply_statcast_to_batter_inputs([p], raw, RETRIEVED_AT)
    assert enriched[0].season.xwoba is None
    assert enriched[0].trends.exit_velocity_trend is None
    assert provenance == []
