from models.batter import BatterInput
from models.pitcher import PitcherInput, RecentStats, SeasonStats
from research.opposing_pitcher_context import (
    attach_opposing_pitcher_context,
    build_opposing_pitcher_index,
)


def _pitcher(player_id, team, game_id, **season_overrides):
    return PitcherInput(
        player_id=player_id, name=f"Pitcher {player_id}", team=team, opponent="XXX", game_id=game_id,
        throwing_hand="R",
        season=SeasonStats(k_percent=24.0, bb_percent=8.0, xera=3.80, xwoba_allowed=0.310,
                            hard_hit_percent=35.0, barrel_percent=7.0, ground_ball_percent=44.0, **season_overrides),
        recent=RecentStats(season_velocity=94.5, csw_percent=None),
    )


def test_opposing_pitcher_mapping_by_game_and_team():
    pitchers = [_pitcher("100", "BBB", "111"), _pitcher("200", "AAA", "111")]
    index = build_opposing_pitcher_index(pitchers)

    batter = BatterInput(player_id="1", name="Hitter", team="AAA", opponent="BBB", game_id="111")
    enriched = attach_opposing_pitcher_context([batter], index)[0]

    # The hitter's OWN team is AAA, opponent is BBB -> they face the pitcher who plays FOR BBB (player 100).
    assert enriched.opposing_pitcher.player_id == "100"
    assert enriched.opposing_pitcher.k_percent == 24.0
    assert enriched.opposing_pitcher.xera == 3.80


def test_opposing_pitcher_never_carries_score_rank_or_tags():
    """Architecture boundary: only raw/contextual fields, never a Pitcher
    Agent conclusion (there is no such field on OpposingPitcherContext at all)."""
    pitchers = [_pitcher("100", "BBB", "111")]
    index = build_opposing_pitcher_index(pitchers)
    batter = BatterInput(player_id="1", name="Hitter", team="AAA", opponent="BBB", game_id="111")
    enriched = attach_opposing_pitcher_context([batter], index)[0]

    context_fields = vars(enriched.opposing_pitcher).keys()
    for forbidden in ("overall_score", "projection", "tags", "reasons", "rank", "risk_score", "confidence"):
        assert forbidden not in context_fields


def test_opposing_pitcher_resolution_does_not_cross_games():
    pitchers = [_pitcher("100", "BBB", "111"), _pitcher("300", "DDD", "222")]
    index = build_opposing_pitcher_index(pitchers)

    batter_game_111 = BatterInput(player_id="1", name="H1", team="AAA", opponent="BBB", game_id="111")
    batter_game_222 = BatterInput(player_id="2", name="H2", team="CCC", opponent="DDD", game_id="222")
    enriched = attach_opposing_pitcher_context([batter_game_111, batter_game_222], index)

    assert enriched[0].opposing_pitcher.player_id == "100"
    assert enriched[1].opposing_pitcher.player_id == "300"


def test_batter_with_no_matching_pitcher_gets_empty_context():
    index = build_opposing_pitcher_index([])
    batter = BatterInput(player_id="1", name="H", team="AAA", opponent="BBB", game_id="999")
    enriched = attach_opposing_pitcher_context([batter], index)[0]
    assert enriched.opposing_pitcher.player_id is None


def test_uses_recent_csw_fallback_when_season_csw_missing():
    p = _pitcher("100", "BBB", "111")
    p.recent = RecentStats(season_velocity=94.5, csw_percent=28.0)  # season csw always None per M5 limitation
    index = build_opposing_pitcher_index([p])
    assert index[("111", "BBB")].csw_percent == 28.0
