from models.pitcher import Availability, PitcherInput, RecentStats, SeasonStats

from native_projections.matchup import OpposingLineupQuality
from native_projections.pitcher_projection import project_pitcher
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION


def make_pitcher(season=None, recent=None, availability=None, **top):
    defaults = dict(player_id="P1", name="Test Pitcher", team="AAA", opponent="BBB")
    defaults.update(top)
    return PitcherInput(
        **defaults,
        season=SeasonStats(**(season or {})),
        recent=RecentStats(**(recent or {})),
        availability=Availability(**(availability or {})),
    )


REALISTIC_SEASON = dict(
    innings=150.0, era=3.80, batters_faced=620, strikeouts=165, walks=48,
    hits_allowed=135, home_runs_allowed=18, hit_by_pitch=6, earned_runs=63,
)


def test_end_to_end_pitcher_projection_is_sane():
    p = make_pitcher(
        season=REALISTIC_SEASON,
        recent=dict(batters_faced=70, strikeouts=20, walks=6, pitch_count_average=92.0),
        availability=dict(confirmed_starter=True, expected_pitch_count=95.0),
    )
    proj = project_pitcher(p)
    assert proj.player_type == "pitcher"
    assert proj.native_ceiling >= proj.native_projection >= proj.native_floor
    assert proj.model_version == NATIVE_PROJECTION_MODEL_VERSION
    assert proj.pitcher_opportunity is not None
    assert proj.pitcher_components is not None
    assert proj.hitter_opportunity is None
    assert proj.hitter_components is None
    assert len(proj.reasons) > 0


def test_projection_is_deterministic_given_same_inputs():
    p1 = make_pitcher(season=REALISTIC_SEASON, availability=dict(confirmed_starter=True, expected_pitch_count=95.0))
    p2 = make_pitcher(season=REALISTIC_SEASON, availability=dict(confirmed_starter=True, expected_pitch_count=95.0))
    proj1 = project_pitcher(p1, generated_at="2026-08-17T00:00:00Z")
    proj2 = project_pitcher(p2, generated_at="2026-08-17T00:00:00Z")
    assert proj1.native_projection == proj2.native_projection
    assert proj1.native_ceiling == proj2.native_ceiling
    assert proj1.native_floor == proj2.native_floor


def test_missing_all_optional_data_does_not_crash():
    p = make_pitcher()
    proj = project_pitcher(p)
    assert proj.native_floor >= 0


def test_weak_opposing_lineup_increases_projection_vs_strong_lineup():
    p = make_pitcher(
        season=REALISTIC_SEASON, availability=dict(confirmed_starter=True, expected_pitch_count=95.0)
    )
    weak = OpposingLineupQuality(team="BBB", hitters_count=6, avg_k_percent=29.0, avg_bb_percent=7.0, avg_iso=0.130, avg_woba=0.290, is_partial=False)
    strong = OpposingLineupQuality(team="BBB", hitters_count=6, avg_k_percent=16.0, avg_bb_percent=9.0, avg_iso=0.210, avg_woba=0.355, is_partial=False)
    weak_proj = project_pitcher(p, opposing_lineup=weak)
    strong_proj = project_pitcher(p, opposing_lineup=strong)
    assert weak_proj.native_projection > strong_proj.native_projection


def test_park_factor_from_game_environment_hurts_pitcher_in_hitter_park():
    p = make_pitcher(season=REALISTIC_SEASON, team="AAA", availability=dict(confirmed_starter=True, expected_pitch_count=95.0))
    neutral = project_pitcher(p, game_environment={"home_team": "AAA", "ballpark": {"park_factor": 100.0}})
    hitter_park = project_pitcher(p, game_environment={"home_team": "AAA", "ballpark": {"park_factor": 120.0}})
    assert hitter_park.native_projection < neutral.native_projection
