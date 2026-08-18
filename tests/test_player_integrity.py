from dfs.models import CanonicalPlayer, DFSPlayer
from dfs.player_integrity import INVALID, VALID, WARNING, summarize, validate_player, validate_pool


def _games():
    return [
        {"game_id": "g1", "home_team_abbr": "COL", "away_team_abbr": "LAD"},
        {"game_id": "g2", "home_team_abbr": "KC", "away_team_abbr": "ATH"},
    ]


def _player(**overrides):
    base = dict(
        dk_player_id="d1", name="Some Player", team="LAD", player_type="hitter", dk_positions=["3B"],
        salary=5000, mlb_player_id=None, opponent="COL", game_id="g1", match_status="unmatched",
    )
    base.update(overrides)
    return DFSPlayer(**base)


def test_fully_consistent_player_is_valid():
    result = validate_player(_player(), {g["game_id"]: g for g in _games()}, {"LAD", "COL", "KC", "ATH"})
    assert result.status == VALID
    assert result.reasons == []


def test_team_equals_opponent_is_invalid():
    result = validate_player(_player(opponent="LAD"), {g["game_id"]: g for g in _games()}, {"LAD", "COL"})
    assert result.status == INVALID


def test_missing_team_is_invalid():
    result = validate_player(_player(team=""), {g["game_id"]: g for g in _games()}, {"LAD", "COL"})
    assert result.status == INVALID


def test_game_id_not_matching_team_opponent_is_invalid():
    # Modeled on the real Max Muncy bug: team/opponent say LAD@COL but
    # game_id points at a completely different matchup (ATH@KC).
    result = validate_player(_player(game_id="g2"), {g["game_id"]: g for g in _games()}, {"LAD", "COL", "KC", "ATH"})
    assert result.status == INVALID
    assert any("does not include" in r for r in result.reasons)


def test_pitcher_type_disagreeing_with_dk_position_is_invalid():
    result = validate_player(
        _player(player_type="hitter", dk_positions=["SP"]), {g["game_id"]: g for g in _games()}, {"LAD", "COL"}
    )
    assert result.status == INVALID


def test_hitter_position_with_pitcher_type_is_invalid():
    result = validate_player(
        _player(player_type="pitcher", dk_positions=["OF"]), {g["game_id"]: g for g in _games()}, {"LAD", "COL"}
    )
    assert result.status == INVALID


def test_matched_identity_team_disagreement_is_a_warning_not_invalid():
    canonical = CanonicalPlayer(mlb_player_id="9001", name="Some Player", team="ATH", opponent="KC",
                                 game_id="g2", player_type="hitter")
    player = _player(match_status="matched", mlb_player_id="9001")
    result = validate_player(
        player, {g["game_id"]: g for g in _games()}, {"LAD", "COL", "KC", "ATH"},
        canonical_by_id={"9001": canonical},
    )
    assert result.status == WARNING


def test_unknown_game_id_is_a_warning():
    result = validate_player(_player(game_id="does-not-exist"), {g["game_id"]: g for g in _games()}, {"LAD", "COL"})
    assert result.status == WARNING


def test_validate_pool_and_summarize_end_to_end():
    players = [
        _player(dk_player_id="d1"),  # valid
        _player(dk_player_id="d2", opponent="LAD"),  # invalid
        _player(dk_player_id="d3", player_type="pitcher", dk_positions=["OF"]),  # invalid
    ]
    results = validate_pool(players, _games())
    summary = summarize(results)
    assert summary["total"] == 3
    assert summary["valid"] == 1
    assert summary["invalid"] == 2
    assert len(summary["invalid_rows"]) == 2
