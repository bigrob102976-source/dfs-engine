"""M6A/M6B/M6C -- scripts/compute_canonical_eligibility.py: the bridge
that runs the REAL dfs/eligibility.py::compute_eligibility() and
dfs/slate_validation.py::match_game_infos() against a canonical Postgres
player list (passed in as plain JSON, since Python never touches
Postgres directly -- see canonical_ingestion/__init__.py). No real
research-package I/O or network access -- ensure_research_package is
monkeypatched to a fixed in-memory package."""

import scripts.compute_canonical_eligibility as bridge
from research.adapters.pitcher_input import ResearchPackageNotFoundError


def _game(game_id, home, away):
    return {"game_id": game_id, "home_team_abbr": home, "away_team_abbr": away}


def _research_pitcher(game_id, player_id, team_abbr="BOS"):
    return {"player_id": player_id, "team_abbr": team_abbr, "opponent_abbr": "TOR", "game_id": game_id}


def _research_batter(game_id, player_id, team_abbr, batting_order):
    return {"player_id": player_id, "team_abbr": team_abbr, "opponent_abbr": "TOR", "game_id": game_id, "batting_order": batting_order}


def _player(provider_player_id, **overrides):
    base = {
        "providerPlayerId": provider_player_id, "name": "Player", "team": "BOS", "opponent": "TOR",
        "positions": ["OF"], "salary": 4500, "identityStatus": "RESOLVED", "mlbPlayerId": "mlb-1",
    }
    base.update(overrides)
    return base


def test_starting_pitcher_eligible_end_to_end(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [_research_pitcher("g1", "mlb-1")], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["P"], identityStatus="RESOLVED", mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)

    assert result["status"] == "OK"
    assert result["results"] == [{"providerPlayerId": "1", "gameId": "g1", "eligibilityStatus": "STARTING_PITCHER", "optimizerEligible": True, "battingOrder": None}]


def test_starting_hitter_gets_batting_order(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [], "batters": [_research_batter("g1", "mlb-1", "BOS", 3)]}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["OF"], mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)

    assert result["results"][0]["eligibilityStatus"] == "STARTING_HITTER"
    assert result["results"][0]["optimizerEligible"] is True
    assert result["results"][0]["battingOrder"] == 3


def test_relief_pitcher_not_eligible(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [_research_pitcher("g1", "someone-else")], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["P"], mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)

    assert result["results"][0]["eligibilityStatus"] == "RELIEF_PITCHER"
    assert result["results"][0]["optimizerEligible"] is False


def test_bench_hitter_when_lineup_posted_but_not_starting(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [], "batters": [_research_batter("g1", "someone-else", "BOS", 1)]}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["OF"], mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["eligibilityStatus"] == "BENCH"
    assert result["results"][0]["optimizerEligible"] is False


def test_lineup_unconfirmed_when_team_lineup_has_not_posted(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["OF"], mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["eligibilityStatus"] == "LINEUP_UNCONFIRMED"
    assert result["results"][0]["optimizerEligible"] is False


def test_unresolved_identity_reports_unmatched_never_blocks(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [_research_pitcher("g1", "mlb-1")], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["P"], identityStatus="UNRESOLVED", mlbPlayerId=None)]}
    result = bridge.compute_for_payload(payload)

    assert result["status"] == "OK"  # servable -- never blocks the slate
    assert result["results"][0]["eligibilityStatus"] == "UNMATCHED"
    assert result["results"][0]["optimizerEligible"] is False


def test_review_required_identity_reports_ambiguous(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", identityStatus="REVIEW_REQUIRED", mlbPlayerId=None)]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["eligibilityStatus"] == "AMBIGUOUS"
    assert result["results"][0]["optimizerEligible"] is False


def test_no_research_package_reported_honestly_never_a_crash(monkeypatch):
    def raise_not_found(date, root):
        raise ResearchPackageNotFoundError("no package for this date")
    monkeypatch.setattr(bridge, "ensure_research_package", raise_not_found)

    payload = {"date": "2026-09-03", "players": [_player("1")]}
    result = bridge.compute_for_payload(payload)

    assert result["status"] == "NO_RESEARCH_PACKAGE"
    assert result["results"] == []


def test_game_id_resolution_uses_real_match_game_infos_team_pair_matching(monkeypatch):
    # Team-pair (frozenset) matching means the "AWAY@HOME" order built
    # from a single player's own team/opponent doesn't need to be correct
    # -- this is the real dfs.slate_validation.match_game_infos() behavior.
    package = {"games": [_game("g7", "BOS", "TOR")], "pitchers": [], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", team="TOR", opponent="BOS")]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["gameId"] == "g7"


def test_player_with_no_opponent_gets_no_game_id_never_guessed(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", opponent=None)]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["gameId"] is None


def test_pitcher_type_inferred_from_dk_positions_reuses_real_helper(monkeypatch):
    package = {"games": [_game("g1", "BOS", "TOR")], "pitchers": [_research_pitcher("g1", "mlb-1")], "batters": []}
    monkeypatch.setattr(bridge, "ensure_research_package", lambda date, root: package)

    payload = {"date": "2026-09-02", "players": [_player("1", positions=["SP"], mlbPlayerId="mlb-1")]}
    result = bridge.compute_for_payload(payload)
    assert result["results"][0]["eligibilityStatus"] == "STARTING_PITCHER"  # only reachable if player_type == "pitcher"
