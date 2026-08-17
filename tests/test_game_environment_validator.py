from research.game_environment.models import (
    EnvironmentScore,
    FutureAdjustmentPreview,
    GameEnvironmentReport,
    GameSummary,
    SlateEnvironmentReport,
    UmpireProfile,
    VegasLine,
    VegasSnapshot,
)
from research.game_environment.validator import validate_game_report, validate_slate_report, validate_vegas_snapshot


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


# ----------------------------------------------------------------------------
# Vegas sanity checks (Milestone 24)
# ----------------------------------------------------------------------------


def _vegas(**overrides) -> VegasSnapshot:
    base = dict(
        game_id="g1", home_team="LAD", away_team="SD", provider_name="SportsGameOdds", is_mock=False, retrieved_at="now",
        opening_home=VegasLine(moneyline=-165, run_line=-1.5, total=8.5),
        opening_away=VegasLine(moneyline=140, run_line=1.5, total=8.5),
        current_home=VegasLine(moneyline=-165, run_line=-1.5, total=8.5),
        current_away=VegasLine(moneyline=140, run_line=1.5, total=8.5),
        home_implied_runs=5.0, away_implied_runs=3.5,
        total_movement=0.0, moneyline_movement_home=0,
        implied_runs_is_valid=True,
    )
    base.update(overrides)
    return VegasSnapshot(**base)


def test_clean_real_vegas_snapshot_has_no_warnings():
    assert validate_vegas_snapshot(_vegas()) == []


def test_total_outside_plausible_range_warns():
    warnings = validate_vegas_snapshot(
        _vegas(current_home=VegasLine(moneyline=-165, run_line=-1.5, total=25.0))
    )
    assert any("outside the plausible" in w for w in warnings)


def test_total_at_boundary_does_not_warn():
    warnings = validate_vegas_snapshot(
        _vegas(
            current_home=VegasLine(moneyline=-165, run_line=-1.5, total=4.0),
            home_implied_runs=2.75, away_implied_runs=1.25,
        )
    )
    assert warnings == []


def test_negative_home_implied_runs_warns():
    warnings = validate_vegas_snapshot(_vegas(home_implied_runs=-1.0))
    assert any("home_implied_runs is negative" in w for w in warnings)


def test_negative_away_implied_runs_warns():
    warnings = validate_vegas_snapshot(_vegas(away_implied_runs=-1.0))
    assert any("away_implied_runs is negative" in w for w in warnings)


def test_implied_runs_not_reconciling_with_total_warns_loudly():
    # 5.0 + 3.5 = 8.5, matches total -- now break it.
    warnings = validate_vegas_snapshot(_vegas(home_implied_runs=6.0))
    assert any("does not reconcile" in w for w in warnings)


def test_implied_runs_within_tolerance_does_not_warn():
    warnings = validate_vegas_snapshot(_vegas(home_implied_runs=5.001, away_implied_runs=3.5))
    assert warnings == []


def test_invalid_flag_with_populated_implied_runs_warns():
    warnings = validate_vegas_snapshot(_vegas(implied_runs_is_valid=False))
    assert any("must never be silently presented as valid" in w for w in warnings)


def test_invalid_flag_with_none_implied_runs_does_not_double_warn_about_presentation():
    warnings = validate_vegas_snapshot(_vegas(implied_runs_is_valid=False, home_implied_runs=None, away_implied_runs=None))
    assert not any("must never be silently presented as valid" in w for w in warnings)


def test_missing_total_is_not_a_range_violation():
    warnings = validate_vegas_snapshot(
        _vegas(current_home=VegasLine(moneyline=-165, run_line=-1.5, total=None), home_implied_runs=None, away_implied_runs=None)
    )
    assert warnings == []


def test_game_report_with_vegas_includes_vegas_warnings():
    warnings = validate_game_report(_game(vegas=_vegas(home_implied_runs=-1.0)))
    assert any("home_implied_runs is negative" in w for w in warnings)


def test_game_report_without_vegas_has_no_vegas_warnings():
    warnings = validate_game_report(_game(vegas=None))
    assert not any("implied_runs" in w or "Vegas total" in w for w in warnings)
