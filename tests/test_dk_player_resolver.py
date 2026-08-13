from dfs.models import DKSalaryRow
from dfs.player_resolver import (
    build_canonical_by_id,
    build_canonical_index,
    build_name_only_index,
    resolve_all,
    resolve_player,
)


def _package():
    return {
        "games": [{"game_id": "111", "home_team_abbr": "BOS", "away_team_abbr": "NYY"}],
        "pitchers": [
            {"player_id": "1001", "name": "Home Ace", "team_abbr": "BOS", "opponent_abbr": "NYY", "game_id": "111"},
        ],
        "batters": [
            {"player_id": "2001", "name": "Aaron Judge", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111"},
            {"player_id": "2002", "name": "Luis García Jr.", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111"},
        ],
    }


def _dk_row(dk_id, name, team, positions=("OF",), salary=5000):
    return DKSalaryRow(dk_player_id=dk_id, name=name, team_abbrev=team, dk_positions=list(positions),
                        salary=salary, game_info="NYY@BOS 07:05PM ET")


def test_exact_name_team_match():
    package = _package()
    row = _dk_row("d1", "Aaron Judge", "NYY")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"
    assert matches[0].match_confidence == "name_team_exact"
    assert matches[0].player_type == "hitter"


def test_suffix_and_accent_formatting_still_matches():
    package = _package()
    row = _dk_row("d2", "Luis Garcia Jr", "NYY")  # DK sometimes drops the accent/period
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2002"


def test_pitcher_match():
    package = _package()
    row = _dk_row("d3", "Home Ace", "BOS", positions=("P",))
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "1001"
    assert matches[0].player_type == "pitcher"


def test_unmatched_when_name_and_team_unknown():
    package = _package()
    row = _dk_row("d4", "Nobody Here", "NYY")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "unmatched"
    assert matches[0].mlb_player_id is None
    # Player type is inferred from DK position for reporting purposes only.
    assert matches[0].player_type == "hitter"


def test_unmatched_pitcher_infers_pitcher_type_from_dk_position():
    package = _package()
    row = _dk_row("d5", "Bullpen Guy", "BOS", positions=("P",))
    matches = resolve_all([row], package)
    assert matches[0].match_status == "unmatched"
    assert matches[0].player_type == "pitcher"


def test_ambiguous_when_two_players_share_normalized_name_and_team():
    package = _package()
    package["batters"].append(
        {"player_id": "2003", "name": "Aaron Judge", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111"}
    )
    row = _dk_row("d6", "Aaron Judge", "NYY")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "ambiguous"
    assert set(matches[0].candidate_mlb_ids) == {"2001", "2003"}


def test_explicit_crosswalk_wins_over_everything_else():
    package = _package()
    row = _dk_row("dkX", "Some Weird DK Name", "NYY")
    crosswalk = {"dkX": "2001"}
    matches = resolve_all([row], package, crosswalk=crosswalk)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"
    assert matches[0].match_confidence == "explicit_crosswalk"


def test_tier4_fallback_matches_by_name_only_when_team_abbreviation_unknown():
    package = _package()
    # DK team abbreviation typo/unknown code -- name is still unique slate-wide.
    row = _dk_row("d7", "Aaron Judge", "ZZZ")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"
    assert matches[0].match_confidence == "name_only_slate_unique"


def test_tier4_fallback_stays_ambiguous_if_name_not_unique_slate_wide():
    package = _package()
    package["batters"].append(
        {"player_id": "3001", "name": "Aaron Judge", "team_abbr": "BOS", "opponent_abbr": "NYY", "game_id": "111"}
    )
    row = _dk_row("d8", "Aaron Judge", "ZZZ")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "ambiguous"


def test_never_fuzzy_matches_unrelated_names():
    package = _package()
    row = _dk_row("d9", "Completely Different Person", "NYY")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "unmatched"


def test_build_canonical_index_and_helpers_are_consistent():
    package = _package()
    index = build_canonical_index(package)
    name_only = build_name_only_index(index)
    by_id = build_canonical_by_id(index)
    assert by_id["2001"].name == "Aaron Judge"
    assert len(name_only[("aaron judge")]) == 1
    row = _dk_row("d10", "Aaron Judge", "NYY")
    match = resolve_player(row, index, name_only, canonical_by_id=by_id)
    assert match.mlb_player_id == "2001"
