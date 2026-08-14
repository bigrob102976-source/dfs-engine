from research.game_environment.ballpark import get_ballpark_profile
from research.game_environment.models import (
    BullpenProfile,
    EnvironmentScore,
    VegasLine,
    VegasSnapshot,
    WeatherAnalysis,
    WeatherConclusion,
)
from research.game_environment.summary import generate_game_summary


def _score(overall: float) -> EnvironmentScore:
    return EnvironmentScore(overall=overall, pitcher=100 - overall, hitter=overall, stack=overall)


def test_headline_is_away_at_home():
    summary = generate_game_summary("ROC", "PHI", _score(50.0), None, None, None, None, None)
    assert summary.headline == "PHI @ ROC"


def test_high_score_produces_excellent_offensive_environment_headline():
    summary = generate_game_summary("ROC", "PHI", _score(94.0), None, None, None, None, None)
    assert summary.bullet_points[0] == "Excellent offensive environment."


def test_low_score_produces_excellent_pitchers_environment_headline():
    summary = generate_game_summary("ROC", "PHI", _score(10.0), None, None, None, None, None)
    assert summary.bullet_points[0] == "Excellent pitcher's environment."


def test_mid_score_produces_balanced_environment_headline():
    summary = generate_game_summary("ROC", "PHI", _score(50.0), None, None, None, None, None)
    assert summary.bullet_points[0] == "Balanced offensive environment."


def test_matches_the_milestones_worked_example():
    park = get_ballpark_profile("COL")  # hitter friendly
    weather = WeatherAnalysis(game_id="g1", conclusions=[WeatherConclusion(code="wind_strong_out", text="Strong wind blowing out.", favors="hitter")])
    vegas = VegasSnapshot(
        game_id="g1", home_team="ROC", away_team="PHI", provider_name="MOCK VEGAS", is_mock=True, retrieved_at="now",
        opening_home=VegasLine(total=10.5), opening_away=VegasLine(total=10.5),
        current_home=VegasLine(total=10.5), current_away=VegasLine(total=10.5),
        home_implied_runs=5.5, away_implied_runs=5.0, total_movement=0.0, moneyline_movement_home=0,
    )
    weak_bullpen = BullpenProfile(team_abbr="ROC", provider_name="MOCK BULLPEN DATA", is_mock=True, strength_score=20.0)

    summary = generate_game_summary("ROC", "PHI", _score(94.0), weather, vegas, park, weak_bullpen, weak_bullpen)

    assert summary.headline == "PHI @ ROC"
    assert "Excellent offensive environment." in summary.bullet_points
    assert "Strong wind blowing out." in summary.bullet_points
    assert "High implied total." in summary.bullet_points
    assert "Weak bullpen." in summary.bullet_points
    assert "Hitter friendly park." in summary.bullet_points
    assert "No rain concerns." in summary.bullet_points


def test_indoor_game_never_claims_no_rain_concerns():
    weather = WeatherAnalysis(game_id="g1", conclusions=[WeatherConclusion(code="indoor_game", text="Indoor game -- weather is not a factor.", favors="neutral")])
    summary = generate_game_summary("TEX", "PHI", _score(60.0), weather, None, None, None, None)
    assert "Indoor game -- weather is not a factor." in summary.bullet_points
    assert "No rain concerns." not in summary.bullet_points


def test_high_rain_delay_risk_replaces_no_rain_concerns():
    weather = WeatherAnalysis(game_id="g1", conclusions=[WeatherConclusion(code="rain_delay_risk", text="High rain delay risk.", favors="risk")])
    summary = generate_game_summary("ROC", "PHI", _score(60.0), weather, None, None, None, None)
    assert "High rain delay risk." in summary.bullet_points
    assert "No rain concerns." not in summary.bullet_points


def test_pitcher_friendly_park_bullet():
    park = get_ballpark_profile("SF")
    summary = generate_game_summary("SF", "PHI", _score(30.0), None, None, park, None, None)
    assert "Pitcher friendly park." in summary.bullet_points


def test_low_total_bullet():
    vegas = VegasSnapshot(
        game_id="g1", home_team="ROC", away_team="PHI", provider_name="MOCK VEGAS", is_mock=True, retrieved_at="now",
        opening_home=VegasLine(total=7.0), opening_away=VegasLine(total=7.0),
        current_home=VegasLine(total=7.0), current_away=VegasLine(total=7.0),
        home_implied_runs=3.5, away_implied_runs=3.5, total_movement=0.0, moneyline_movement_home=0,
    )
    summary = generate_game_summary("ROC", "PHI", _score(30.0), None, vegas, None, None, None)
    assert "Low implied total." in summary.bullet_points


def test_strong_bullpen_bullet():
    strong_bullpen = BullpenProfile(team_abbr="ROC", provider_name="MOCK BULLPEN DATA", is_mock=True, strength_score=85.0)
    summary = generate_game_summary("ROC", "PHI", _score(40.0), None, None, None, strong_bullpen, strong_bullpen)
    assert "Strong bullpen." in summary.bullet_points


def test_missing_everything_still_produces_a_headline_and_environment_bullet_never_crashes():
    summary = generate_game_summary("ROC", "PHI", _score(50.0), None, None, None, None, None)
    assert summary.headline == "PHI @ ROC"
    assert len(summary.bullet_points) == 1
