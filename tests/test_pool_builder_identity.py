"""Canonical MLB Player Identity Foundation -- integration tests for
dfs/pool_builder.py::build_pool()'s widened identity resolution.

Every test here explicitly supplies its own crosswalk (via monkeypatch
on dfs.pool_builder.load_crosswalk) rather than touching the real
on-disk default -- see tests/test_pool_builder.py's autouse fixture,
which this file does NOT use since these tests need to control the
crosswalk contents directly.
"""

import json
from pathlib import Path

from dfs import pool_builder
from dfs.models import DKSalaryRow
from dfs.pool_builder import build_pool
from player_identity.models import CanonicalIdentity


def _write_research_package(root: Path, date: str, batters=None, pitchers=None):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    games = [{
        "game_id": "g1", "date": date, "game_datetime_utc": "2026-08-23T23:05:00Z", "status": "scheduled",
        "home_team_id": "1", "home_team_abbr": "BOS", "away_team_id": "2", "away_team_abbr": "TOR",
        "venue_id": "v1", "venue_name": "Fenway", "home_probable_pitcher_id": "p2", "away_probable_pitcher_id": None,
        "game_number": 1,
    }]
    teams = [
        {"team_id": "1", "abbreviation": "BOS", "name": "Boston Red Sox"},
        {"team_id": "2", "abbreviation": "TOR", "name": "Toronto Blue Jays"},
    ]
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps(pitchers or []), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps(batters or []), encoding="utf-8")


def _identity(mlb_id, name, team, player_type):
    return CanonicalIdentity(
        mlb_player_id=mlb_id, canonical_name=name, normalized_name=name.lower(),
        current_team=team, player_type=player_type, last_verified_at="2026-08-23T18:00:00+00:00",
    )


def _with_crosswalk(monkeypatch, crosswalk: dict):
    monkeypatch.setattr(pool_builder, "load_crosswalk", lambda *a, **k: crosswalk)


def test_identity_resolves_independent_of_lineup_confirmation(tmp_path, monkeypatch):
    # No pitchers.json/batters.json entries at all (nothing confirmed
    # yet) -- the ONLY identity source is the roster-derived crosswalk.
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")
    _with_crosswalk(monkeypatch, {"h1": _identity("h1", "Bench Hitter", "BOS", "hitter")})

    rows = [DKSalaryRow(dk_player_id="d1", name="Bench Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    player = result.players[0]
    assert player.match_status == "matched"
    assert player.mlb_player_id == "h1"


def test_active_roster_hitter_resolves_before_lineup_posts(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")  # no confirmed batters yet
    _with_crosswalk(monkeypatch, {"h1": _identity("h1", "Early Hitter", "BOS", "hitter")})

    rows = [DKSalaryRow(dk_player_id="d1", name="Early Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    player = result.players[0]
    assert player.mlb_player_id == "h1"
    assert player.eligibility_status == "LINEUP_UNCONFIRMED"
    assert player.optimizer_eligible is False


def test_bench_player_identity_resolved_but_not_eligible(tmp_path, monkeypatch):
    # BOS's lineup HAS posted (one confirmed starter), but this hitter
    # is NOT among the confirmed starters -- a genuine bench player.
    research_root = tmp_path / "research_output"
    batters = [{"player_id": "starter1", "name": "Confirmed Starter", "team_id": "1", "team_abbr": "BOS",
                "opponent_team_id": "2", "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1,
                "position": "CF", "bats": "L", "status": "starting_lineup", "source": "mlb_stats_api"}]
    _write_research_package(research_root, "2026-08-23", batters=batters)
    _with_crosswalk(monkeypatch, {
        "starter1": _identity("starter1", "Confirmed Starter", "BOS", "hitter"),
        "bench1": _identity("bench1", "Bench Guy", "BOS", "hitter"),
    })

    rows = [
        DKSalaryRow(dk_player_id="d1", name="Confirmed Starter", team_abbrev="BOS", dk_positions=["OF"], salary=5000, game_info="TOR@BOS 7:05PM ET"),
        DKSalaryRow(dk_player_id="d2", name="Bench Guy", team_abbrev="BOS", dk_positions=["1B"], salary=3000, game_info="TOR@BOS 7:05PM ET"),
    ]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    bench = next(p for p in result.players if p.name == "Bench Guy")
    assert bench.mlb_player_id == "bench1"  # identity resolved
    assert bench.eligibility_status == "BENCH"
    assert bench.optimizer_eligible is False

    starter = next(p for p in result.players if p.name == "Confirmed Starter")
    assert starter.eligibility_status == "STARTING_HITTER"
    assert starter.optimizer_eligible is True


def test_reliever_identity_resolved_but_not_eligible(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    pitchers = [{"player_id": "starter1", "name": "Probable Starter", "team_id": "2", "team_abbr": "TOR",
                 "opponent_team_id": "1", "opponent_abbr": "BOS", "game_id": "g1", "throws": "R",
                 "status": "probable", "source": "mlb_stats_api"}]
    _write_research_package(research_root, "2026-08-23", pitchers=pitchers)
    _with_crosswalk(monkeypatch, {
        "starter1": _identity("starter1", "Probable Starter", "TOR", "pitcher"),
        "reliever1": _identity("reliever1", "Setup Man", "TOR", "pitcher"),
    })

    rows = [
        DKSalaryRow(dk_player_id="d1", name="Probable Starter", team_abbrev="TOR", dk_positions=["P"], salary=9000, game_info="TOR@BOS 7:05PM ET"),
        DKSalaryRow(dk_player_id="d2", name="Setup Man", team_abbrev="TOR", dk_positions=["RP"], salary=3500, game_info="TOR@BOS 7:05PM ET"),
    ]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    reliever = next(p for p in result.players if p.name == "Setup Man")
    assert reliever.mlb_player_id == "reliever1"
    assert reliever.eligibility_status == "RELIEF_PITCHER"
    assert reliever.optimizer_eligible is False

    starter = next(p for p in result.players if p.name == "Probable Starter")
    assert starter.eligibility_status == "STARTING_PITCHER"
    assert starter.optimizer_eligible is True


def test_probable_starter_still_resolves_correctly_with_a_crosswalk_present(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    pitchers = [{"player_id": "p1", "name": "Ace Pitcher", "team_id": "2", "team_abbr": "TOR",
                 "opponent_team_id": "1", "opponent_abbr": "BOS", "game_id": "g1", "throws": "L",
                 "status": "probable", "source": "mlb_stats_api"}]
    _write_research_package(research_root, "2026-08-23", pitchers=pitchers)
    # Crosswalk ALSO knows this same player (as it would in reality --
    # he's on the roster too) -- must not create a duplicate/ambiguous match.
    _with_crosswalk(monkeypatch, {"p1": _identity("p1", "Ace Pitcher", "TOR", "pitcher")})

    rows = [DKSalaryRow(dk_player_id="d1", name="Ace Pitcher", team_abbrev="TOR", dk_positions=["P"], salary=9500, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    player = result.players[0]
    assert player.match_status == "matched"
    assert player.eligibility_status == "STARTING_PITCHER"
    assert player.optimizer_eligible is True


def test_same_name_different_team_stays_safe(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")
    _with_crosswalk(monkeypatch, {
        "1": _identity("1", "Max Muncy", "BOS", "hitter"),
        "2": _identity("2", "Max Muncy", "TOR", "hitter"),
    })

    rows = [
        DKSalaryRow(dk_player_id="d1", name="Max Muncy", team_abbrev="BOS", dk_positions=["1B"], salary=4000, game_info="TOR@BOS 7:05PM ET"),
        DKSalaryRow(dk_player_id="d2", name="Max Muncy", team_abbrev="TOR", dk_positions=["1B"], salary=4200, game_info="TOR@BOS 7:05PM ET"),
    ]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    bos_player = next(p for p in result.players if p.dk_player_id == "d1")
    tor_player = next(p for p in result.players if p.dk_player_id == "d2")
    assert bos_player.mlb_player_id == "1"
    assert tor_player.mlb_player_id == "2"
    assert bos_player.match_status == "matched"
    assert tor_player.match_status == "matched"


def test_same_name_same_team_is_ambiguous_never_guessed(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")
    _with_crosswalk(monkeypatch, {
        "1": _identity("1", "John Smith", "BOS", "hitter"),
        "2": _identity("2", "John Smith", "BOS", "hitter"),
    })

    rows = [DKSalaryRow(dk_player_id="d1", name="John Smith", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    player = result.players[0]
    assert player.match_status == "ambiguous"
    assert player.mlb_player_id is None
    assert player.optimizer_eligible is False


def test_dk_player_id_explicit_crosswalk_mapping_still_wins_over_roster_identity(tmp_path, monkeypatch):
    # Tier 1 (explicit dk_player_id -> mlb_player_id crosswalk) must
    # still take priority over the roster-derived candidates -- this
    # milestone only ADDS candidates, it never changes tier order.
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")
    _with_crosswalk(monkeypatch, {"wrong_id": _identity("wrong_id", "Ambiguous Name", "BOS", "hitter")})

    rows = [DKSalaryRow(dk_player_id="d1", name="Ambiguous Name", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"), crosswalk={"d1": "explicit_correct_id"})

    assert result.players[0].mlb_player_id == "explicit_correct_id"


def test_optimizer_eligible_pool_never_includes_an_unconfirmed_hitter_even_with_wider_identity(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-23")
    _with_crosswalk(monkeypatch, {"h1": _identity("h1", "Early Hitter", "BOS", "hitter")})

    rows = [DKSalaryRow(dk_player_id="d1", name="Early Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    assert result.active_pool == []  # identity resolved, but still correctly excluded from the optimizer pool


def test_team_alias_normalization_applies_to_roster_derived_identity_too(tmp_path, monkeypatch):
    # DraftKings exports "ARI"; our research package (and therefore the
    # roster-derived crosswalk, keyed by the SAME teams.json abbreviation
    # convention) uses "AZ" -- reuses dfs/team_abbreviations.py's
    # existing alias table, never a second one (see this milestone's
    # explicit "do not create a duplicate abbreviation map" instruction).
    research_root = tmp_path / "research_output"
    folder = research_root / "2026-08-23"
    folder.mkdir(parents=True, exist_ok=True)
    games = [{
        "game_id": "g1", "date": "2026-08-23", "game_datetime_utc": "2026-08-23T23:05:00Z", "status": "scheduled",
        "home_team_id": "9", "home_team_abbr": "AZ", "away_team_id": "1", "away_team_abbr": "BOS",
        "venue_id": "v1", "venue_name": "Chase Field", "home_probable_pitcher_id": None, "away_probable_pitcher_id": None,
        "game_number": 1,
    }]
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps([
        {"team_id": "9", "abbreviation": "AZ", "name": "Arizona Diamondbacks"},
        {"team_id": "1", "abbreviation": "BOS", "name": "Boston Red Sox"},
    ]), encoding="utf-8")
    (folder / "pitchers.json").write_text("[]", encoding="utf-8")
    (folder / "batters.json").write_text("[]", encoding="utf-8")

    _with_crosswalk(monkeypatch, {"h1": _identity("h1", "Desert Hitter", "AZ", "hitter")})

    # DK's own row says "ARI", never "AZ".
    rows = [DKSalaryRow(dk_player_id="d1", name="Desert Hitter", team_abbrev="ARI", dk_positions=["OF"], salary=4000, game_info="BOS@ARI 7:05PM ET")]
    result = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    assert result.players[0].mlb_player_id == "h1"
    assert result.players[0].match_status == "matched"


def test_widened_identity_never_changes_a_confirmed_starters_eligibility(tmp_path, monkeypatch):
    # Regression guard: adding roster candidates must not perturb the
    # ALREADY-correct eligibility of a confirmed starter.
    research_root = tmp_path / "research_output"
    batters = [{"player_id": "h1", "name": "Leadoff Hitter", "team_id": "1", "team_abbr": "BOS",
                "opponent_team_id": "2", "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1,
                "position": "CF", "bats": "L", "status": "starting_lineup", "source": "mlb_stats_api"}]
    _write_research_package(research_root, "2026-08-23", batters=batters)
    crosswalk = {"h1": _identity("h1", "Leadoff Hitter", "BOS", "hitter")}

    _with_crosswalk(monkeypatch, {})
    rows = [DKSalaryRow(dk_player_id="d1", name="Leadoff Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET")]
    baseline = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    _with_crosswalk(monkeypatch, crosswalk)
    widened = build_pool(rows, "2026-08-23", str(research_root), str(tmp_path / "predictions"))

    assert baseline.players[0].eligibility_status == widened.players[0].eligibility_status == "STARTING_HITTER"
    assert baseline.players[0].optimizer_eligible == widened.players[0].optimizer_eligible is True
