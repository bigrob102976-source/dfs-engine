from research.game_environment.models import (
    EnvironmentScore,
    FutureAdjustmentPreview,
    GameEnvironmentReport,
    GameSummary,
    SlateEnvironmentReport,
    UmpireProfile,
)
from research.game_environment.validator import validate_game_report, validate_slate_report


def _game(**overrides) -> GameEnvironmentReport:
    base = dict(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc="2026-08-13T23:00:00Z", venue_name="Citizens Bank Park",
        environment_score=EnvironmentScore(overall=60.0, pitcher=40.0, hitter=60.0, stack=62.0),
        summary=GameSummary(headline="COL @ PHI", bullet_points=["Balanced offensive environment."]),
        future_adjustment_preview=FutureAdjustmentPreview(enabled=False),
    )
    base.update(overrides)
    return GameEnvironmentReport(**base)


def test_a_clean_game_report_has_no_warnings():
    assert validate_game_report(_game()) == []


def test_missing_game_id_warns():
    warnings = validate_game_report(_game(game_id=""))
    assert any("game_id" in w for w in warnings)


def test_missing_teams_warns():
    warnings = validate_game_report(_game(home_team="", away_team=""))
    assert any("home_team/away_team" in w for w in warnings)


def test_out_of_range_score_warns():
    warnings = validate_game_report(_game(environment_score=EnvironmentScore(overall=150.0, pitcher=40.0, hitter=60.0, stack=62.0)))
    assert any("overall" in w for w in warnings)


def test_negative_score_warns():
    warnings = validate_game_report(_game(environment_score=EnvironmentScore(overall=60.0, pitcher=-10.0, hitter=60.0, stack=62.0)))
    assert any("pitcher" in w for w in warnings)


def test_unrecognized_umpire_status_warns():
    warnings = validate_game_report(_game(umpire=UmpireProfile(game_id="g1", status="MAYBE")))
    assert any("umpire status" in w for w in warnings)


def test_known_umpire_status_never_warns():
    warnings = validate_game_report(_game(umpire=UmpireProfile(game_id="g1", status="KNOWN")))
    assert warnings == []


def test_unknown_umpire_status_never_warns():
    warnings = validate_game_report(_game(umpire=UmpireProfile(game_id="g1", status="UNKNOWN")))
    assert warnings == []


def test_missing_summary_headline_warns():
    warnings = validate_game_report(_game(summary=GameSummary(headline="", bullet_points=[])))
    assert any("summary headline" in w for w in warnings)


def test_empty_slate_warns():
    report = SlateEnvironmentReport(slate_date="2026-08-13", generated_at="now", engine_version="0.1.0", games=[])
    warnings = validate_slate_report(report)
    assert any("zero games" in w for w in warnings)


def test_slate_report_aggregates_every_games_warnings():
    report = SlateEnvironmentReport(slate_date="2026-08-13", generated_at="now", engine_version="0.1.0", games=[_game(game_id=""), _game()])
    warnings = validate_slate_report(report)
    assert any("game_id" in w for w in warnings)
