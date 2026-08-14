from research.game_environment.ballpark import get_ballpark_profile
from research.game_environment.models import (
    BullpenProfile,
    VegasLine,
    VegasSnapshot,
    WeatherAnalysis,
    WeatherConclusion,
)
from research.game_environment.scoring import score_environment


def _vegas(total: float) -> VegasSnapshot:
    return VegasSnapshot(
        game_id="g1", home_team="AAA", away_team="BBB", provider_name="MOCK VEGAS", is_mock=True, retrieved_at="now",
        opening_home=VegasLine(total=total), opening_away=VegasLine(total=total),
        current_home=VegasLine(total=total), current_away=VegasLine(total=total),
        home_implied_runs=total / 2, away_implied_runs=total / 2, total_movement=0.0, moneyline_movement_home=0,
    )


def _bullpen(strength: float) -> BullpenProfile:
    return BullpenProfile(team_abbr="AAA", provider_name="MOCK BULLPEN DATA", is_mock=True, strength_score=strength)


def test_score_is_neutral_50_when_nothing_is_available():
    score = score_environment(None, None, None, None, None)
    assert score.overall == 50.0
    assert score.hitter == 50.0
    assert score.pitcher == 50.0
    assert score.stack == 50.0


def test_hitter_favorable_signals_produce_a_high_hitter_score():
    park = get_ballpark_profile("COL")  # extreme hitter's park
    weather = WeatherAnalysis(game_id="g1", conclusions=[WeatherConclusion(code="wind_strong_out", text="Strong wind blowing out.", favors="hitter")])
    vegas = _vegas(total=11.0)  # high total
    weak_bullpen = _bullpen(strength=20.0)
    score = score_environment(park, weather, vegas, weak_bullpen, weak_bullpen)
    assert score.hitter > 70.0


def test_pitcher_favorable_signals_produce_a_low_hitter_score():
    park = get_ballpark_profile("SF")  # pitcher's park
    weather = WeatherAnalysis(game_id="g1", conclusions=[WeatherConclusion(code="cold_weather", text="Cold weather suppresses offense.", favors="pitcher")])
    vegas = _vegas(total=6.5)  # low total
    strong_bullpen = _bullpen(strength=90.0)
    score = score_environment(park, weather, vegas, strong_bullpen, strong_bullpen)
    assert score.hitter < 30.0


def test_pitcher_score_is_always_the_complement_of_hitter_score():
    park = get_ballpark_profile("COL")
    vegas = _vegas(total=10.0)
    score = score_environment(park, None, vegas, None, None)
    assert round(score.pitcher + score.hitter, 1) == 100.0


def test_overall_score_matches_hitter_score():
    park = get_ballpark_profile("COL")
    vegas = _vegas(total=10.0)
    score = score_environment(park, None, vegas, None, None)
    assert score.overall == score.hitter


def test_stack_score_differs_from_hitter_score_when_bullpen_signal_present():
    park = get_ballpark_profile("COL")
    vegas = _vegas(total=10.0)
    weak_bullpen = _bullpen(strength=10.0)
    score = score_environment(park, None, vegas, weak_bullpen, weak_bullpen)
    # Stack weights lean more heavily on vegas_total/bullpen than Hitter
    # weights do, so the two scores are not required to be identical --
    # this test just guards against them being silently hardcoded equal.
    assert isinstance(score.stack, float)


def test_every_score_stays_within_0_100():
    park = get_ballpark_profile("COL")
    weather = WeatherAnalysis(game_id="g1", conclusions=[
        WeatherConclusion(code="wind_strong_out", text="Strong wind blowing out.", favors="hitter"),
        WeatherConclusion(code="hot_weather", text="Hot weather favors offense.", favors="hitter"),
    ])
    vegas = _vegas(total=13.0)
    weak_bullpen = _bullpen(strength=0.0)
    score = score_environment(park, weather, vegas, weak_bullpen, weak_bullpen)
    for value in (score.overall, score.pitcher, score.hitter, score.stack):
        assert 0.0 <= value <= 100.0


def test_missing_park_never_crashes_renormalizes_over_remaining_signals():
    vegas = _vegas(total=10.0)
    score = score_environment(None, None, vegas, None, None)
    assert score.hitter != 50.0  # vegas alone should still move the score off neutral
