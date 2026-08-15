from projection_engine.scoring import build_ai_player_projection, build_ai_projection_document, build_ai_projection_slate, grade_for


def _board_record(**overrides):
    base = dict(
        player_id="h1", name="Test Hitter", team="NYY", opponent="BOS", game_id="g1",
        projection=10.0, ceiling=18.0, floor=5.0, overall_score=60.0, risk_score=30.0,
        confidence=80.0, matchup_score=50.0, recent_trend_score=50.0, tags=[],
    )
    base.update(overrides)
    return base


def _game(**overrides):
    base = dict(
        game_id="g1", home_team="NYY", away_team="BOS",
        weather=None, weather_analysis=None,
        vegas={"current_home": {"total": 8.5}, "home_implied_runs": 4.3, "away_implied_runs": 4.2, "total_movement": None},
        bullpen_home=None, bullpen_away=None, ballpark=None,
    )
    base.update(overrides)
    return base


# ----------------------------------------------------------------------------
# grade_for
# ----------------------------------------------------------------------------


def test_grade_for_bands():
    assert grade_for(95.0) == "A+"
    assert grade_for(85.0) == "A"
    assert grade_for(75.0) == "B+"
    assert grade_for(65.0) == "B"
    assert grade_for(55.0) == "C+"
    assert grade_for(45.0) == "C"
    assert grade_for(30.0) == "D"
    assert grade_for(5.0) == "F"


def test_grade_for_none_returns_none():
    assert grade_for(None) is None


# ----------------------------------------------------------------------------
# build_ai_player_projection
# ----------------------------------------------------------------------------


def test_missing_independent_projection_returns_none():
    record = _board_record(projection=None)
    assert build_ai_player_projection(record, "hitter") is None


def test_no_signals_ai_projection_equals_independent():
    record = _board_record()
    player = build_ai_player_projection(record, "hitter")
    assert player.ai_projection == 10.0
    assert player.total_adjustment == 0.0
    assert player.signals == []


def test_ai_projection_never_goes_negative():
    record = _board_record(projection=0.1, ceiling=1.0, floor=0.0)
    ownership_row = {"projected_ownership": 60.0, "leverage_score": -50.0}
    player = build_ai_player_projection(record, "hitter", ownership_row=ownership_row)
    assert player.ai_projection >= 0.0


def test_ceiling_and_floor_move_proportionally():
    record = _board_record(projection=10.0, ceiling=20.0, floor=5.0)
    ownership_row = {"projected_ownership": 5.0, "leverage_score": 40.0}  # fires leverage bonus
    player = build_ai_player_projection(record, "hitter", ownership_row=ownership_row)
    assert player.ai_projection > 10.0
    ratio = player.ai_projection / 10.0
    assert round(player.ai_ceiling / 20.0, 3) == round(ratio, 3)
    assert round(player.ai_floor / 5.0, 3) == round(ratio, 3)


def test_ai_value_score_computed_from_salary():
    record = _board_record(projection=10.0)
    player = build_ai_player_projection(record, "hitter", salary=4000)
    assert player.ai_value_score == round((player.ai_projection / 4000) * 1000.0, 2)


def test_ai_value_score_none_without_salary():
    record = _board_record()
    player = build_ai_player_projection(record, "hitter", salary=None)
    assert player.ai_value_score is None


def test_external_and_adjusted_projections_pass_through_unmodified():
    record = _board_record()
    adjusted_row = {"external_projection": 11.5, "adjusted_projection": 10.8, "adjustment_confidence": 70.0}
    player = build_ai_player_projection(record, "hitter", adjusted_row=adjusted_row)
    assert player.external_projection == 11.5
    assert player.adjusted_projection == 10.8
    assert player.independent_projection == 10.0  # never mutated


def test_weather_signal_flows_through_game_context():
    record = _board_record()
    game = _game(
        weather={"current": {"wind_speed_mph": 14.0}},
        weather_analysis={"conclusions": [{"code": "wind_strong_out", "text": "Strong wind blowing out.", "favors": "hitter"}]},
    )
    player = build_ai_player_projection(record, "hitter", game=game)
    assert any(s.category == "weather" for s in player.signals)
    assert player.ai_projection > 10.0


def test_total_adjustment_percent_capped_at_max():
    from config.projection_engine_config import MAX_TOTAL_ADJUSTMENT_PERCENT

    record = _board_record(projection=5.0, matchup_score=100.0, recent_trend_score=100.0)
    game = _game(
        weather={"current": {"wind_speed_mph": 20.0}},
        weather_analysis={"conclusions": [{"code": "wind_strong_out", "text": "Strong wind blowing out.", "favors": "hitter"}]},
        vegas={"current_home": {"total": 12.0}, "home_implied_runs": 7.0, "away_implied_runs": 5.0, "total_movement": 3.0},
        bullpen_away={"strength_score": 10.0, "estimated_fatigue": "high"},
        ballpark={"hr_factor": 130, "venue_name": "Bandbox Park"},
    )
    ownership_row = {"projected_ownership": 2.0, "leverage_score": 90.0}
    adjusted_row = {"external_projection": 20.0, "adjustment_confidence": 90.0}
    player = build_ai_player_projection(record, "hitter", game=game, ownership_row=ownership_row, adjusted_row=adjusted_row)
    assert abs(player.total_adjustment_percent) <= MAX_TOTAL_ADJUSTMENT_PERCENT + 0.01
    assert player.adjustment_capped is True


def test_reasons_and_summary_are_populated():
    record = _board_record()
    game = _game(
        weather={"current": {"wind_speed_mph": 14.0}},
        weather_analysis={"conclusions": [{"code": "wind_strong_out", "text": "Strong wind blowing out.", "favors": "hitter"}]},
    )
    player = build_ai_player_projection(record, "hitter", game=game)
    assert len(player.reasons) > 0
    assert player.name in player.ai_summary


# ----------------------------------------------------------------------------
# build_ai_projection_slate / build_ai_projection_document
# ----------------------------------------------------------------------------


def test_build_ai_projection_slate_combines_pitchers_and_hitters():
    pitcher_snapshot = {"pitchers": [_board_record(player_id="p1", name="Test Pitcher", team="BOS", opponent="NYY")]}
    batter_snapshot = {"hitters": [_board_record(player_id="h1", name="Test Hitter")]}
    records, warnings = build_ai_projection_slate(pitcher_snapshot, batter_snapshot)
    assert len(records) == 2
    assert warnings == []
    types = {r.player_type for r in records}
    assert types == {"pitcher", "hitter"}


def test_build_ai_projection_slate_skips_and_warns_missing_projection():
    pitcher_snapshot = {"pitchers": []}
    batter_snapshot = {"hitters": [_board_record(player_id="h1", projection=None)]}
    records, warnings = build_ai_projection_slate(pitcher_snapshot, batter_snapshot)
    assert records == []
    assert len(warnings) == 1
    assert "Test Hitter" in warnings[0]


def test_build_ai_projection_slate_joins_environment_ownership_adjusted_and_salary():
    pitcher_snapshot = {"pitchers": []}
    batter_snapshot = {"hitters": [_board_record(player_id="h1")]}
    environment_report = {"games": [_game()]}
    ownership_snapshot = {"players": [{"mlb_player_id": "h1", "projected_ownership": 5.0, "leverage_score": 40.0}]}
    adjusted_snapshot = {"records": [{"independent_player_id": "h1", "external_projection": 12.0, "adjusted_projection": 11.0}]}
    pool_doc = {"players": [{"mlb_player_id": "h1", "salary": 4500}]}

    records, warnings = build_ai_projection_slate(
        pitcher_snapshot, batter_snapshot,
        environment_report=environment_report, ownership_snapshot=ownership_snapshot,
        adjusted_snapshot=adjusted_snapshot, pool_doc=pool_doc,
    )
    assert warnings == []
    [player] = records
    assert player.external_projection == 12.0
    assert player.adjusted_projection == 11.0
    assert player.salary == 4500
    assert any(s.category == "ownership" for s in player.signals)


def test_build_ai_projection_document_shape():
    pitcher_snapshot = {"pitchers": []}
    batter_snapshot = {"hitters": [_board_record(player_id="h1")]}
    records, warnings = build_ai_projection_slate(pitcher_snapshot, batter_snapshot)
    document = build_ai_projection_document("2026-08-14", records, warnings, generated_at="2026-08-14T18:00:00+00:00")
    assert document["slate_date"] == "2026-08-14"
    assert document["player_count"] == 1
    assert len(document["players"]) == 1
    assert document["players"][0]["player_id"] == "h1"
    assert document["warnings"] == []
