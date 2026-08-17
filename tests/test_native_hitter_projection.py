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
