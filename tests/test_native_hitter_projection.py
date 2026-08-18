from models.batter import BatterInput, OpposingPitcherContext, RecentBattingStats, SeasonBattingStats

from native_projections.hitter_projection import project_hitter
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION


def make_batter(season=None, recent=None, opposing_pitcher=None, **top):
    defaults = dict(player_id="B1", name="Test Hitter", team="AAA", opponent="BBB", batting_order=3, position="OF")
    defaults.update(top)
    return BatterInput(
        **defaults,
        season=SeasonBattingStats(**(season or {})),
        recent=RecentBattingStats(**(recent or {})),
        opposing_pitcher=OpposingPitcherContext(**(opposing_pitcher or {})),
    )


REALISTIC_SEASON = dict(
    plate_appearances=450, at_bats=400, hits=110, doubles=24, triples=2, home_runs=18,
    walks=42, strikeouts=95, stolen_bases=6, obp=0.345, iso=0.220,
)


def test_end_to_end_hitter_projection_is_sane():
    b = make_batter(season=REALISTIC_SEASON, recent=dict(plate_appearances=55, k_percent=19.0, bb_percent=10.0))
    proj = project_hitter(b)
    assert proj.player_type == "hitter"
    assert proj.native_projection > 0
    assert proj.native_ceiling >= proj.native_projection >= proj.native_floor
    assert proj.model_version == NATIVE_PROJECTION_MODEL_VERSION
    assert proj.hitter_opportunity is not None
    assert proj.hitter_components is not None
    assert proj.pitcher_opportunity is None
    assert proj.pitcher_components is None
    assert len(proj.reasons) > 0


def test_tiny_sample_hitter_does_not_project_like_a_superstar():
    # The documented Andrew Pinckney-type case: 10 PA, 1 HR.
    pinckney = make_batter(season=dict(plate_appearances=10, at_bats=9, hits=1, doubles=0, triples=0, home_runs=1, walks=1, strikeouts=2))
    proj = project_hitter(pinckney)
    # A real elite, full-season slugger's native_projection should land
    # meaningfully higher than this tiny-sample player's regressed one.
    star = make_batter(season=REALISTIC_SEASON)
    star_proj = project_hitter(star)
    assert proj.native_projection < star_proj.native_projection


def test_projection_is_deterministic_given_same_inputs():
    b1 = make_batter(season=REALISTIC_SEASON)
    b2 = make_batter(season=REALISTIC_SEASON)
    proj1 = project_hitter(b1, generated_at="2026-08-17T00:00:00Z")
    proj2 = project_hitter(b2, generated_at="2026-08-17T00:00:00Z")
    assert proj1.native_projection == proj2.native_projection
    assert proj1.native_ceiling == proj2.native_ceiling
    assert proj1.native_floor == proj2.native_floor
    assert proj1.confidence == proj2.confidence


def test_missing_all_optional_data_does_not_crash():
    b = make_batter()
    proj = project_hitter(b)
    assert proj.native_projection >= 0
    assert proj.native_floor >= 0


def test_mock_vegas_never_influences_projection_even_with_implied_runs_present():
    # Milestone 24: a mock Vegas snapshot must never move the projection,
    # even though it carries a (synthetic) implied_runs value.
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    no_vegas = project_hitter(b, game_environment={"home_team": "AAA"})
    mock_vegas = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            "vegas": {"is_mock": True, "home_implied_runs": 6.5, "implied_runs_is_valid": True},
        },
    )
    assert mock_vegas.native_projection == no_vegas.native_projection


def test_real_vegas_does_influence_projection():
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    no_vegas = project_hitter(b, game_environment={"home_team": "AAA"})
    real_vegas = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            "vegas": {"is_mock": False, "home_implied_runs": 6.5, "implied_runs_is_valid": True},
        },
    )
    assert real_vegas.native_projection != no_vegas.native_projection


def test_invalid_vegas_calculation_contributes_zero_and_warns():
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    no_vegas = project_hitter(b, game_environment={"home_team": "AAA"})
    invalid_vegas = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            # An invalid calculation, per providers/implied_runs.py's own
            # contract, always carries home_implied_runs=None alongside
            # implied_runs_is_valid=False -- never a populated value.
            "vegas": {"is_mock": False, "home_implied_runs": None, "away_implied_runs": None, "implied_runs_is_valid": False},
        },
    )
    assert invalid_vegas.native_projection == no_vegas.native_projection
    assert any("invalid" in w.lower() for w in invalid_vegas.warnings)


def test_frozen_pregame_vegas_influences_projection_same_as_live_pregame():
    # Milestone 25: a PREGAME_FROZEN snapshot is shaped identically to a
    # LIVE_PREGAME one by the time it reaches project_hitter() -- real
    # implied runs, is_mock=False -- so it must influence the projection
    # exactly the same way. No new gating code exists for this
    # distinction; this proves the existing is_mock/implied-runs gate is
    # sufficient.
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    live = project_hitter(
        b, game_environment={"home_team": "AAA", "vegas": {"is_mock": False, "home_implied_runs": 6.5, "implied_runs_is_valid": True, "vegas_projection_status": "LIVE_PREGAME"}}
    )
    frozen = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            "vegas": {"is_mock": False, "home_implied_runs": 6.5, "implied_runs_is_valid": True, "vegas_projection_status": "PREGAME_FROZEN", "is_frozen_pregame": True},
        },
    )
    assert frozen.native_projection == live.native_projection


def test_in_play_only_vegas_never_influences_projection():
    # Milestone 25: vegas.py's SportsGameOddsVegasProvider.get_vegas_line()
    # never populates home_implied_runs/away_implied_runs for an
    # IN_PLAY_ONLY snapshot (see test_vegas_pregame_lock.py) -- this
    # confirms the shape it DOES produce (implied runs None,
    # vegas_projection_status "IN_PLAY_ONLY") is correctly a zero-influence
    # no-op at the projection layer, covering the exact Dodgers extreme
    # in-play scenario Milestone 24's live validation found.
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    no_vegas = project_hitter(b, game_environment={"home_team": "AAA"})
    in_play_only = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            "vegas": {"is_mock": False, "home_implied_runs": None, "away_implied_runs": None, "implied_runs_is_valid": False, "vegas_projection_status": "IN_PLAY_ONLY"},
        },
    )
    assert in_play_only.native_projection == no_vegas.native_projection
    assert any("in-play" in w.lower() for w in in_play_only.warnings)


def test_missing_pregame_vegas_never_influences_projection():
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    no_vegas = project_hitter(b, game_environment={"home_team": "AAA"})
    missing = project_hitter(
        b,
        game_environment={
            "home_team": "AAA",
            "vegas": {"is_mock": False, "home_implied_runs": None, "away_implied_runs": None, "implied_runs_is_valid": False, "vegas_projection_status": "MISSING"},
        },
    )
    assert missing.native_projection == no_vegas.native_projection
    assert any("unavailable" in w.lower() for w in missing.warnings)


def test_park_factor_from_game_environment_shifts_projection():
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    neutral = project_hitter(b, game_environment={"home_team": "AAA", "ballpark": {"park_factor": 100.0}})
    hitter_friendly = project_hitter(b, game_environment={"home_team": "AAA", "ballpark": {"park_factor": 120.0}})
    assert hitter_friendly.native_projection > neutral.native_projection


def test_weather_favors_hitter_included_in_reasons():
    b = make_batter(season=REALISTIC_SEASON, team="AAA")
    game_report = {
        "home_team": "AAA",
        "weather_analysis": {"conclusions": [{"favors": "hitter"}, {"favors": "hitter"}]},
        "weather": {"is_mock": True},
    }
    proj = project_hitter(b, game_environment=game_report)
    assert any("weather" in r.lower() for r in proj.reasons)
