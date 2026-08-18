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


def test_unmatched_sp_infers_pitcher_type_from_dk_position():
    # Milestone 27.3 regression: DraftKings' real "Position" column uses
    # SP/RP, never a bare "P" -- the fallback classifier used to check
    # for literal "P" membership and mis-classified every unmatched SP/RP
    # row as a hitter.
    package = _package()
    row = _dk_row("d11", "Some Ace", "BOS", positions=("SP",))
    matches = resolve_all([row], package)
    assert matches[0].match_status == "unmatched"
    assert matches[0].player_type == "pitcher"


def test_unmatched_rp_infers_pitcher_type_from_dk_position():
    package = _package()
    row = _dk_row("d12", "Some Reliever", "BOS", positions=("RP",))
    matches = resolve_all([row], package)
    assert matches[0].player_type == "pitcher"


def test_unmatched_of_infers_hitter_type_from_dk_position():
    package = _package()
    row = _dk_row("d13", "Some Outfielder", "NYY", positions=("OF",))
    matches = resolve_all([row], package)
    assert matches[0].player_type == "hitter"


def test_multi_position_hitter_remains_hitter():
    package = _package()
    row = _dk_row("d14", "Some Utility Guy", "NYY", positions=("2B", "SS", "OF"))
    matches = resolve_all([row], package)
    assert matches[0].player_type == "hitter"


def test_dk_position_is_authoritative_even_for_a_matched_player():
    # DK position eligibility wins even over the matched canonical
    # record's own player_type -- never inferred from which research
    # board matched or from MLB defensive position.
    package = _package()
    row = _dk_row("d15", "Aaron Judge", "NYY", positions=("SP",))
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"
    assert matches[0].player_type == "pitcher"


def test_cross_team_name_collision_does_not_silently_match_the_wrong_team():
    # Milestone 27.3 regression, modeled on the real Max Muncy case: two
    # DIFFERENT DK rows share a name but belong to two different teams,
    # and only ONE of those teams has a canonical (research-confirmed)
    # record. Tier 4's name-only fallback must not guess which is which.
    package = _package()
    package["batters"].append(
        {"player_id": "9001", "name": "Max Muncy", "team_abbr": "ATH", "opponent_abbr": "KC", "game_id": "999"}
    )
    package["games"].append({"game_id": "999", "home_team_abbr": "KC", "away_team_abbr": "ATH"})
    lad_row = _dk_row("d16", "Max Muncy", "LAD", positions=("3B",))
    ath_row = _dk_row("d17", "Max Muncy", "ATH", positions=("3B",))
    matches = resolve_all([lad_row, ath_row], package)
    lad_match, ath_match = matches

    # The genuinely canonical ATH row still resolves normally.
    assert ath_match.match_status == "matched"
    assert ath_match.mlb_player_id == "9001"

    # The LAD row must NOT borrow the ATH player's identity.
    assert lad_match.mlb_player_id != "9001"
    assert lad_match.match_status == "unmatched"
    assert lad_match.player_type == "hitter"  # still correct via DK position, just not MLB-matched


def test_team_abbreviation_alias_case_still_matches_via_tier4():
    # The legitimate case Tier 4 exists for (a single DK row whose team
    # abbreviation the index doesn't recognize, name unique slate-wide)
    # must keep working after the cross-team-collision guard was added.
    package = _package()
    row = _dk_row("d18", "Aaron Judge", "ZZZ")
    matches = resolve_all([row], package)
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"


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
