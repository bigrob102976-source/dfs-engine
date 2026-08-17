from models.batter import BatterInput, SeasonBattingStats
from models.pitcher import Availability, PitcherInput, RecentStats

from native_projections.playing_time import project_hitter_opportunity, project_pitcher_opportunity


def make_batter(batting_order=None, **top):
    defaults = dict(player_id="B1", name="Test Hitter", team="AAA", opponent="BBB", batting_order=batting_order)
    defaults.update(top)
    return BatterInput(**defaults, season=SeasonBattingStats())


def make_pitcher(availability=None, recent=None, **top):
    defaults = dict(player_id="P1", name="Test Pitcher", team="AAA", opponent="BBB")
    defaults.update(top)
    return PitcherInput(
        **defaults,
        availability=Availability(**(availability or {})),
        recent=RecentStats(**(recent or {})),
    )


# ----------------------------------------------------------------------------
# Hitter expected PA / batting-order effect
# ----------------------------------------------------------------------------


def test_leadoff_hitter_gets_more_expected_pa_than_ninth_hitter():
    leadoff = project_hitter_opportunity(make_batter(batting_order=1))
    ninth = project_hitter_opportunity(make_batter(batting_order=9))
    assert leadoff.expected_pa > ninth.expected_pa


def test_expected_pa_decreases_monotonically_down_the_order():
    values = [project_hitter_opportunity(make_batter(batting_order=n)).expected_pa for n in range(1, 10)]
    assert values == sorted(values, reverse=True)


def test_confirmed_batting_order_gets_full_confidence():
    opp = project_hitter_opportunity(make_batter(batting_order=3))
    assert opp.pa_confidence > 0
    assert "confirmed lineup" in opp.reasons[0].lower()


def test_unconfirmed_lineup_gets_zero_confidence_and_fallback_pa():
    opp = project_hitter_opportunity(make_batter(batting_order=None))
    assert opp.pa_confidence == 0.0
    assert any("not yet posted" in r.lower() for r in opp.reasons)


# ----------------------------------------------------------------------------
# Pitcher workload
# ----------------------------------------------------------------------------


def test_confirmed_starter_with_real_pitch_count_gets_highest_confidence():
    opp = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 95.0})
    )
    assert opp.expected_pitch_count == 95.0
    assert opp.workload_confidence > 50.0


def test_falls_back_to_recent_pitch_count_average_when_no_confirmed_target():
    opp = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True}, recent={"pitch_count_average": 88.0})
    )
    assert opp.expected_pitch_count == 88.0
    assert any("recent-starts average" in r for r in opp.reasons)


def test_falls_back_to_league_default_when_no_pitch_count_data_at_all():
    opp = project_pitcher_opportunity(make_pitcher(availability={"confirmed_starter": True}))
    assert opp.expected_pitch_count == 90.0
    assert any("league-average default" in r for r in opp.reasons)


def test_unconfirmed_starter_reduces_workload_confidence():
    confirmed = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 95.0})
    )
    unconfirmed = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": False, "expected_pitch_count": 95.0})
    )
    assert unconfirmed.workload_confidence < confirmed.workload_confidence


def test_unknown_starter_status_also_reduces_confidence():
    confirmed = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 95.0})
    )
    unknown = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": None, "expected_pitch_count": 95.0})
    )
    assert unknown.workload_confidence < confirmed.workload_confidence


def test_expected_innings_is_clamped_to_configured_range():
    tiny = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 10.0})
    )
    huge = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 400.0})
    )
    assert tiny.expected_innings >= 2.5
    assert huge.expected_innings <= 7.5


def test_expected_batters_faced_scales_with_expected_innings():
    opp = project_pitcher_opportunity(
        make_pitcher(availability={"confirmed_starter": True, "expected_pitch_count": 95.0})
    )
    assert opp.expected_batters_faced > opp.expected_innings
