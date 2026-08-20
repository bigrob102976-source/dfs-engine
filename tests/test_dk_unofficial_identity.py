"""Identity matching tests for the unofficial DraftKings provider.
MLB reuses dfs/player_resolver.py against a real research package
shape; every other sport is expected to report "unmatched" by design
(no canonical identity system exists for them yet)."""

from draftkings_unofficial.identity import identity_match_summary, match_draftables
from draftkings_unofficial.models import DkDraftable


def _draftable(draftable_id, name, team, position="OF", salary=4000, player_id=None):
    return DkDraftable(
        draftable_id=draftable_id, draft_group_id=1, player_id=player_id, player_dk_id=player_id,
        display_name=name, first_name=None, last_name=None, position=position, roster_slot_id=1,
        salary=salary, status="None", team_id=1, team_abbreviation=team, competition_id=1,
    )


def _research_package():
    return {
        "games": [{"game_id": "g1", "home_team_abbr": "BOS", "away_team_abbr": "TOR"}],
        "teams": [{"team_id": "1", "abbreviation": "BOS"}, {"team_id": "2", "abbreviation": "TOR"}],
        "pitchers": [
            {"player_id": "p1", "name": "Away Ace", "team_id": "2", "team_abbr": "TOR", "opponent_team_id": "1",
             "opponent_abbr": "BOS", "game_id": "g1", "status": "probable"},
        ],
        "batters": [
            {"player_id": "h1", "name": "Leadoff Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
             "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1, "position": "CF", "status": "starting_lineup"},
        ],
    }


def test_mlb_matches_a_confirmed_starter_by_name_team():
    draftables = [_draftable(1, "Leadoff Hitter", "BOS", position="OF")]
    matches = match_draftables(draftables, "MLB", research_package=_research_package())
    assert len(matches) == 1
    assert matches[0].match_status == "matched"
    assert matches[0].canonical_player_id == "h1"
    assert matches[0].sport_code == "MLB"


def test_mlb_unmatched_player_preserved_not_dropped():
    draftables = [_draftable(1, "Nobody Real", "BOS", position="OF")]
    matches = match_draftables(draftables, "MLB", research_package=_research_package())
    assert len(matches) == 1
    assert matches[0].match_status == "unmatched"
    assert matches[0].draftable_id == 1


def test_non_mlb_sport_always_reports_unmatched_by_design():
    draftables = [_draftable(1, "Some NFL Player", "KC", position="QB")]
    matches = match_draftables(draftables, "NFL", research_package=_research_package())
    assert len(matches) == 1
    assert matches[0].match_status == "unmatched"
    assert matches[0].canonical_player_id is None


def test_mlb_without_research_package_reports_unmatched_not_error():
    draftables = [_draftable(1, "Leadoff Hitter", "BOS")]
    matches = match_draftables(draftables, "MLB", research_package=None)
    assert matches[0].match_status == "unmatched"


def test_empty_draftables_returns_empty():
    assert match_draftables([], "MLB", research_package=_research_package()) == []


def test_order_preserved():
    draftables = [_draftable(1, "Leadoff Hitter", "BOS"), _draftable(2, "Away Ace", "TOR", position="SP")]
    matches = match_draftables(draftables, "MLB", research_package=_research_package())
    assert [m.draftable_id for m in matches] == [1, 2]


def test_identity_match_summary_counts_and_percent():
    draftables = [
        _draftable(1, "Leadoff Hitter", "BOS"),
        _draftable(2, "Nobody Real", "BOS"),
        _draftable(3, "Also Fake", "BOS"),
        _draftable(4, "Still Fake", "BOS"),
    ]
    matches = match_draftables(draftables, "MLB", research_package=_research_package())
    summary = identity_match_summary(matches)
    assert summary["total"] == 4
    assert summary["matched"] == 1
    assert summary["match_percent"] == 25.0


def test_identity_match_summary_empty():
    assert identity_match_summary([]) == {"total": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "match_percent": 0.0}
