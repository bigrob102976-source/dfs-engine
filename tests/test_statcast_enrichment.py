import pytest

from models.pitcher import PitcherInput
from research.statcast_collector import RawStatcastData
from research.statcast_enrichment import (
    SeasonLeaderboardIndex,
    apply_statcast_to_pitcher_inputs,
    compute_trends,
    index_season_leaderboards,
    parse_recent_statcast,
    parse_season_statcast,
)

RETRIEVED_AT = "2026-08-11T12:00:00+00:00"


def _pitch(pitch_type, description, release_speed=None, bb_type=None, launch_speed=None, launch_speed_angle=None, date=None):
    return {
        "pitch_type": pitch_type, "description": description, "release_speed": release_speed,
        "bb_type": bb_type, "launch_speed": launch_speed, "launch_speed_angle": launch_speed_angle,
        "game_date": date,
    }


# 10 pitches across 2 games: 6 FF (5 "clean" pitches + 1 batted ball), 4 SL.
# Hand-verified expectations (see milestone dev notes):
#   velocity (FF only)   = mean(95.0, 95.5, 94.8, 95.3, 96.0, 95.2) = 95.3
#   csw%  = (2 called_strike + 1 swinging_strike + 1 swinging_strike_blocked) / 10 = 40.0
#   swstr% = (1 swinging_strike + 1 swinging_strike_blocked) / 10 = 20.0
#   3 balls in play: exit velos 90/100/93 -> avg 94.3, hard_hit 1/3=33.3%, barrel(lsa=6) 1/3=33.3%, GB 1/3=33.3%
#   pitch mix: FF 6/10=60%, SL 4/10=40%; 2 distinct game dates
_RECENT_PITCH_ROWS = [
    _pitch("FF", "called_strike", release_speed="95.0", date="2026-07-31"),
    _pitch("FF", "swinging_strike", release_speed="95.5", date="2026-07-31"),
    _pitch("FF", "ball", release_speed="94.8", date="2026-07-31"),
    _pitch("SL", "foul", release_speed="85.0", date="2026-07-31"),
    _pitch("SL", "hit_into_play", release_speed="84.5", bb_type="ground_ball", launch_speed="90.0", launch_speed_angle="2", date="2026-08-05"),
    _pitch("FF", "hit_into_play", release_speed="95.3", bb_type="fly_ball", launch_speed="100.0", launch_speed_angle="6", date="2026-08-05"),
    _pitch("FF", "called_strike", release_speed="96.0", date="2026-08-05"),
    _pitch("SL", "swinging_strike_blocked", release_speed="84.0", date="2026-08-05"),
    _pitch("FF", "ball", release_speed="95.2", date="2026-08-05"),
    _pitch("SL", "hit_into_play", release_speed="83.9", bb_type="line_drive", launch_speed="93.0", launch_speed_angle="3", date="2026-08-05"),
]


# ----------------------------------------------------------------------------
# Recent (pitch-level) parsing
# ----------------------------------------------------------------------------


def test_parse_recent_statcast_velocity_is_fastball_only():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.velocity == pytest.approx(95.3, abs=0.05)


def test_parse_recent_statcast_csw_percent():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.csw_percent == 40.0  # (2 called_strike + 2 whiffs) / 10 pitches


def test_parse_recent_statcast_swinging_strike_percent():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.swinging_strike_percent == 20.0  # 2 whiffs / 10 pitches


def test_parse_recent_statcast_ground_ball_percent():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.ground_ball_percent == pytest.approx(33.3, abs=0.1)  # 1 of 3 balls in play


def test_parse_recent_statcast_hard_hit_percent():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.hard_hit_percent == pytest.approx(33.3, abs=0.1)  # only the 100mph batted ball qualifies (>=95)


def test_parse_recent_statcast_barrel_percent_uses_statcast_classification():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.barrel_percent == pytest.approx(33.3, abs=0.1)  # only launch_speed_angle == "6" counts


def test_parse_recent_statcast_pitch_mix_and_sample_size():
    line = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert line.pitch_mix == {"FF": 60.0, "SL": 40.0}
    assert line.sample_size_pitches == 10
    assert line.starts_covered == 2


@pytest.mark.parametrize("rows", [None, []])
def test_parse_recent_statcast_handles_missing_data(rows):
    assert parse_recent_statcast(rows, "9001", "2026", RETRIEVED_AT) is None


def test_parse_recent_statcast_zero_balls_in_play_is_safe():
    only_pitches = [_pitch("FF", "called_strike", release_speed="95.0", date="2026-08-05")]
    line = parse_recent_statcast(only_pitches, "9001", "2026", RETRIEVED_AT)
    assert line.hard_hit_percent is None
    assert line.barrel_percent is None
    assert line.ground_ball_percent is None


# ----------------------------------------------------------------------------
# Season (leaderboard) parsing
# ----------------------------------------------------------------------------


def _season_index(**overrides):
    expected = [{"player_id": "9001", "est_ba": ".250", "est_woba": ".310", "xera": "3.80"}]
    custom = [{
        "player_id": "9001", "pa": "400", "swing_percent": "46.0", "whiff_percent": "25.0",
        "groundballs_percent": "45.0", "hard_hit_percent": "35.0", "barrel_batted_rate": "7.0",
        "exit_velocity_avg": "88.5",
    }]
    arsenal = [{"pitcher": "9001", "ff_avg_speed": "95.0", "si_avg_speed": ""}]
    arsenal_stats = [
        {"player_id": "9001", "pitch_type": "FF", "pitch_usage": "55.0"},
        {"player_id": "9001", "pitch_type": "SL", "pitch_usage": "45.0"},
    ]
    raw = RawStatcastData(
        date="2026-08-11", season="2026",
        expected_statistics=overrides.get("expected", expected),
        custom_leaderboard=overrides.get("custom", custom),
        pitch_arsenals=overrides.get("arsenal", arsenal),
        pitch_arsenal_stats=overrides.get("arsenal_stats", arsenal_stats),
    )
    return index_season_leaderboards(raw)


def test_parse_season_statcast_xera_xwoba_xba():
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.xera == 3.80
    assert line.xwoba == 0.310
    assert line.xba == 0.250


def test_parse_season_statcast_velocity_uses_four_seam():
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.velocity == 95.0


def test_parse_season_statcast_velocity_falls_back_to_sinker():
    idx = _season_index(arsenal=[{"pitcher": "9001", "ff_avg_speed": "", "si_avg_speed": "93.5"}])
    line = parse_season_statcast(idx, "9001", "2026", RETRIEVED_AT)
    assert line.velocity == 93.5


def test_parse_season_statcast_swinging_strike_is_derived_not_savant_whiff():
    # swing_percent(46.0) * whiff_percent(25.0) / 100 = 11.5, NOT Savant's raw
    # whiff_percent (25.0), which is misses-PER-SWING and would badly break
    # the existing 6-16% swstr scale if used directly.
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.swinging_strike_percent == pytest.approx(11.5)


def test_parse_season_statcast_season_csw_is_never_populated():
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.csw_percent is None


def test_parse_season_statcast_ground_ball_hard_hit_barrel():
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.ground_ball_percent == 45.0
    assert line.hard_hit_percent == 35.0
    assert line.barrel_percent == 7.0


def test_parse_season_statcast_pitch_mix():
    line = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert line.pitch_mix == {"FF": 55.0, "SL": 45.0}


def test_parse_season_statcast_returns_none_when_player_in_no_leaderboard():
    idx = _season_index()
    assert parse_season_statcast(idx, "9999", "2026", RETRIEVED_AT) is None


def test_parse_season_statcast_partial_availability_leaves_missing_fields_none():
    idx = _season_index(expected=[])  # no xERA/xwOBA/xBA source at all for this player
    line = parse_season_statcast(idx, "9001", "2026", RETRIEVED_AT)
    assert line is not None  # still built from custom/arsenal data
    assert line.xera is None
    assert line.xba is None
    assert line.hard_hit_percent == 35.0  # unaffected


# ----------------------------------------------------------------------------
# Trends
# ----------------------------------------------------------------------------


def test_compute_trends_velocity_and_swstr():
    season = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    recent = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    trends = compute_trends(season, recent)
    assert trends["velocity_trend"] == pytest.approx(95.3 - 95.0, abs=0.05)
    assert trends["swinging_strike_trend"] == pytest.approx(20.0 - 11.5, abs=0.05)


def test_compute_trends_hard_hit_and_barrel_are_inverted_so_positive_is_favorable():
    season = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    recent = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    trends = compute_trends(season, recent)
    # season hard_hit=35.0, recent hard_hit=33.3 -> recent LOWER (better) -> positive trend
    assert trends["hard_hit_trend"] > 0
    # season barrel=7.0, recent barrel=33.3 -> recent HIGHER (worse) -> negative trend
    assert trends["barrel_trend"] < 0


def test_compute_trends_csw_always_none_this_milestone():
    season = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    recent = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)
    assert compute_trends(season, recent)["csw_trend"] is None


def test_compute_trends_pitch_mix_change():
    season = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)  # FF 55 / SL 45
    recent = parse_recent_statcast(_RECENT_PITCH_ROWS, "9001", "2026", RETRIEVED_AT)  # FF 60 / SL 40
    trends = compute_trends(season, recent)
    assert trends["pitch_mix_change"] == pytest.approx(10.0, abs=0.1)  # |60-55| + |40-45|


def test_compute_trends_missing_either_side_gives_none():
    season = parse_season_statcast(_season_index(), "9001", "2026", RETRIEVED_AT)
    assert compute_trends(season, None) == {
        "velocity_trend": None, "csw_trend": None, "swinging_strike_trend": None,
        "hard_hit_trend": None, "barrel_trend": None, "ground_ball_trend": None, "pitch_mix_change": None,
    }


# ----------------------------------------------------------------------------
# Merge into PitcherInput
# ----------------------------------------------------------------------------


def test_apply_statcast_merges_season_and_recent_and_sets_legacy_season_velocity_field():
    raw = RawStatcastData(
        date="2026-08-11", season="2026",
        expected_statistics=[{"player_id": "9001", "est_ba": ".250", "est_woba": ".310", "xera": "3.80"}],
        custom_leaderboard=[{
            "player_id": "9001", "pa": "400", "swing_percent": "46.0", "whiff_percent": "25.0",
            "groundballs_percent": "45.0", "hard_hit_percent": "35.0", "barrel_batted_rate": "7.0", "exit_velocity_avg": "88.5",
        }],
        pitch_arsenals=[{"pitcher": "9001", "ff_avg_speed": "95.0", "si_avg_speed": ""}],
        pitch_arsenal_stats=[{"player_id": "9001", "pitch_type": "FF", "pitch_usage": "55.0"}],
        recent_pitch_level={"9001": _RECENT_PITCH_ROWS},
    )
    p = PitcherInput(player_id="9001", name="Test", team="AAA", opponent="BBB")
    enriched, provenance = apply_statcast_to_pitcher_inputs([p], raw, RETRIEVED_AT)

    entry = enriched[0]
    assert entry.season.xera == 3.80
    assert entry.season.hard_hit_percent == 35.0
    assert entry.recent.velocity == pytest.approx(95.3, abs=0.05)
    # This is the pre-existing (Milestone 2) field agents/pitcher_agent.py's
    # velocity_change calculation reads -- must be populated by name, not a new field.
    assert entry.recent.season_velocity == 95.0
    assert entry.trends.velocity_trend is not None

    types = {rec["type"] for rec in provenance}
    assert types == {"season_statcast", "recent_statcast", "trends"}


def test_apply_statcast_leaves_pitcher_unenriched_when_no_data_available():
    raw = RawStatcastData(date="2026-08-11", season="2026")  # nothing fetched
    p = PitcherInput(player_id="9002", name="Nobody", team="AAA", opponent="BBB")
    enriched, provenance = apply_statcast_to_pitcher_inputs([p], raw, RETRIEVED_AT)

    assert enriched[0].season.xera is None
    assert enriched[0].recent.velocity is None
    assert enriched[0].trends.velocity_trend is None
    assert provenance == []
