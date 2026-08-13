import json
from pathlib import Path

import pytest

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import PROVIDER_FACTORIES, get_configured_provider
from dfs.providers.mock_provider import MockProvider, _mock_salary
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult


def _write_research_package(root: Path, date: str, include_batters: bool = True):
    folder = root / date
    folder.mkdir(parents=True)
    games = [{
        "game_id": "g1", "date": date, "game_datetime_utc": "2026-08-11T23:05:00Z", "status": "scheduled",
        "home_team_id": "1", "home_team_abbr": "BOS", "away_team_id": "2", "away_team_abbr": "TOR",
        "venue_id": "v1", "venue_name": "Fenway", "home_probable_pitcher_id": "p2", "away_probable_pitcher_id": "p1",
        "game_number": 1,
    }]
    teams = [
        {"team_id": "1", "abbreviation": "BOS", "name": "Boston Red Sox"},
        {"team_id": "2", "abbreviation": "TOR", "name": "Toronto Blue Jays"},
    ]
    pitchers = [
        {"player_id": "p1", "name": "Away Ace", "team_id": "2", "team_abbr": "TOR", "opponent_team_id": "1",
         "opponent_abbr": "BOS", "game_id": "g1", "throws": "R", "status": "probable", "source": "mlb_stats_api"},
        {"player_id": "p2", "name": "Home Ace", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "throws": "L", "status": "probable", "source": "mlb_stats_api"},
    ]
    batters = [
        {"player_id": "h1", "name": "Leadoff Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1, "position": "CF", "bats": "L",
         "status": "starting_lineup", "source": "mlb_stats_api"},
        {"player_id": "h2", "name": "Cleanup Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 4, "position": "1B", "bats": "R",
         "status": "starting_lineup", "source": "mlb_stats_api"},
        {"player_id": "h3", "name": "DH Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 5, "position": "DH", "bats": "R",
         "status": "starting_lineup", "source": "mlb_stats_api"},
    ]
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps(pitchers), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps(batters if include_batters else []), encoding="utf-8")


def _write_pitcher_snapshot(root: Path, date: str, timestamp: str = "20260811T180000"):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "slate_date": date, "generated_at": "2026-08-11T18:00:00+00:00", "model_version": "0.6.0",
        "pitchers": [
            {"player_id": "p1", "name": "Away Ace", "team": "TOR", "opponent": "BOS", "overall_score": 90.0},
            {"player_id": "p2", "name": "Home Ace", "team": "BOS", "opponent": "TOR", "overall_score": 30.0},
        ],
    }
    (folder / f"pitcher_board_{timestamp}.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_batter_snapshot(root: Path, date: str, timestamp: str = "20260811T180000"):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "slate_date": date, "generated_at": "2026-08-11T18:00:00+00:00", "model_version": "0.1.0",
        "hitters": [
            {"player_id": "h1", "name": "Leadoff Hitter", "team": "BOS", "opponent": "TOR", "overall_score": 80.0},
            {"player_id": "h2", "name": "Cleanup Hitter", "team": "BOS", "opponent": "TOR", "overall_score": 50.0},
            {"player_id": "h3", "name": "DH Hitter", "team": "BOS", "opponent": "TOR", "overall_score": 20.0},
        ],
    }
    (folder / f"batter_board_{timestamp}.json").write_text(json.dumps(doc), encoding="utf-8")


# ----------------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------------


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        DFSSalaryProvider()


def test_mock_provider_implements_interface():
    assert isinstance(MockProvider(), DFSSalaryProvider)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------


def test_config_falls_back_to_mock_when_unset(monkeypatch):
    """Milestone 15: unset must never leave the dashboard stuck asking
    for a terminal command -- it defaults to the mock provider."""
    monkeypatch.delenv("DFS_SALARY_PROVIDER", raising=False)
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert provider.name == "mock_dev_provider"
    assert reason is None
    assert source == "automatic_fallback"


def test_config_falls_back_to_mock_when_only_whitespace(monkeypatch):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "   ")
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert provider.name == "mock_dev_provider"
    assert source == "automatic_fallback"


def test_config_resolves_explicit_mock_provider(monkeypatch):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "mock")
    provider, reason, source = get_configured_provider()
    assert reason is None
    assert provider is not None
    assert provider.name == "mock_dev_provider"
    assert source == "explicit"


def test_config_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "MOCK")
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert source == "explicit"


def test_config_explicit_provider_overrides_fallback(monkeypatch):
    """A registered non-mock provider, once configured, must be used
    instead of the automatic mock fallback (Milestone 15's explicit
    override requirement)."""
    class _FakeRealProvider(DFSSalaryProvider):
        name = "real_provider"
        requires_api_key = False

        def get_slate(self, date, sport="MLB", site="draftkings"):
            raise NotImplementedError

    monkeypatch.setitem(PROVIDER_FACTORIES, "real_provider", _FakeRealProvider)
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "real_provider")
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert provider.name == "real_provider"
    assert source == "explicit"
    assert reason is None


def test_config_reports_unknown_provider_name_without_falling_back_to_mock(monkeypatch):
    """An explicit but invalid provider name is a real misconfiguration
    -- it must be reported, never silently masked by the mock fallback
    (a typo should be visible, not quietly replaced)."""
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "sportsdataio")
    provider, reason, source = get_configured_provider()
    assert provider is None
    assert "not a recognized provider" in reason
    assert "sportsdataio" in reason
    assert source == "explicit"


def test_config_reports_missing_api_key_without_falling_back_to_mock(monkeypatch):
    class _FakeKeyedProvider(DFSSalaryProvider):
        name = "fake_keyed"
        requires_api_key = True

        def get_slate(self, date, sport="MLB", site="draftkings"):
            raise NotImplementedError

    monkeypatch.setitem(PROVIDER_FACTORIES, "fake_keyed", _FakeKeyedProvider)
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "fake_keyed")
    monkeypatch.delenv("DFS_PROVIDER_API_KEY", raising=False)
    provider, reason, source = get_configured_provider()
    assert provider is None
    assert "DFS_PROVIDER_API_KEY" in reason
    assert source == "explicit"


def test_config_never_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DFS_SALARY_PROVIDER", raising=False)
    # Must not raise -- automatic mock fallback is the expected, reportable state.
    get_configured_provider()


def test_config_never_raises_for_explicit_misconfiguration(monkeypatch):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "totally-unknown")
    # Must not raise -- an explicit-but-invalid provider is also a normal, reportable state.
    get_configured_provider()


# ----------------------------------------------------------------------------
# Mock provider
# ----------------------------------------------------------------------------


def test_mock_provider_builds_real_identities_from_research_package(tmp_path):
    _write_research_package(tmp_path / "research_output", "2026-08-11")
    provider = MockProvider(research_output_root=str(tmp_path / "research_output"), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")

    assert len(result.slates) == 1
    slate = result.slates[0]
    players = result.players_by_slate[slate.slate_id]
    names = {p.name for p in players}
    assert names == {"Away Ace", "Home Ace", "Leadoff Hitter", "Cleanup Hitter", "DH Hitter"}


def test_mock_provider_raises_unavailable_without_research_package(tmp_path):
    provider = MockProvider(research_output_root=str(tmp_path / "research_output"), predictions_root=str(tmp_path / "predictions"))
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-11")


def test_mock_provider_rejects_non_mlb_sport(tmp_path):
    _write_research_package(tmp_path / "research_output", "2026-08-11")
    provider = MockProvider(research_output_root=str(tmp_path / "research_output"), predictions_root=str(tmp_path / "predictions"))
    with pytest.raises(ProviderNoSlateError):
        provider.get_slate("2026-08-11", sport="NFL")


def test_mock_provider_salary_is_deterministic_function_of_overall_score(tmp_path):
    root = tmp_path / "research_output"
    predictions = tmp_path / "predictions"
    _write_research_package(root, "2026-08-11")
    _write_pitcher_snapshot(predictions, "2026-08-11")
    _write_batter_snapshot(predictions, "2026-08-11")
    provider = MockProvider(research_output_root=str(root), predictions_root=str(predictions))
    result = provider.get_slate("2026-08-11")
    players = {p.name: p for p in result.players_by_slate[result.slates[0].slate_id]}

    # Higher overall_score -> higher mock salary, for the same player type.
    assert players["Away Ace"].salary > players["Home Ace"].salary  # 90 vs 30 overall_score
    assert players["Leadoff Hitter"].salary > players["Cleanup Hitter"].salary > players["DH Hitter"].salary

    # Re-running produces identical salaries -- deterministic, not random.
    result2 = provider.get_slate("2026-08-11")
    players2 = {p.name: p for p in result2.players_by_slate[result2.slates[0].slate_id]}
    assert players["Away Ace"].salary == players2["Away Ace"].salary


def test_mock_salary_is_bounded_for_extreme_scores():
    assert _mock_salary("pitcher", 0.0) >= 4500
    assert _mock_salary("pitcher", 100.0) <= 11000
    assert _mock_salary("hitter", 0.0) >= 2000
    assert _mock_salary("hitter", 100.0) <= 6500


def test_mock_salary_falls_back_to_neutral_score_when_none():
    # None must not crash and must land near the base salary.
    salary = _mock_salary("hitter", None)
    assert 2000 <= salary <= 6500


def test_mock_provider_position_mapping(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11")
    provider = MockProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")
    players = {p.name: p for p in result.players_by_slate[result.slates[0].slate_id]}

    assert players["Leadoff Hitter"].position_eligibility == ["OF"]  # CF -> OF
    assert players["Cleanup Hitter"].position_eligibility == ["1B"]
    assert players["Away Ace"].position_eligibility == ["P"]
    # DH has no real DK defensive slot -- documented fallback, not invented eligibility.
    assert players["DH Hitter"].position_eligibility == ["OF"]


def test_mock_provider_game_string_uses_et_and_team_pair(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11")
    provider = MockProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")
    players = {p.name: p for p in result.players_by_slate[result.slates[0].slate_id]}
    assert players["Away Ace"].game == "TOR@BOS 7:05PM ET"


def test_mock_provider_warns_when_lineups_not_posted(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11", include_batters=False)
    provider = MockProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")
    assert any("lineup" in w.lower() for w in result.warnings)


def test_mock_provider_no_games_returns_empty_slates_not_an_error(tmp_path):
    root = tmp_path / "research_output"
    (root / "2026-08-11").mkdir(parents=True)
    (root / "2026-08-11" / "games.json").write_text("[]", encoding="utf-8")
    (root / "2026-08-11" / "teams.json").write_text("[]", encoding="utf-8")
    (root / "2026-08-11" / "pitchers.json").write_text("[]", encoding="utf-8")
    (root / "2026-08-11" / "batters.json").write_text("[]", encoding="utf-8")
    provider = MockProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")
    assert result.slates == []
    assert any("no mlb games" in w.lower() for w in result.warnings)


def test_mock_provider_provenance_fields_present(tmp_path):
    root = tmp_path / "research_output"
    _write_research_package(root, "2026-08-11")
    provider = MockProvider(research_output_root=str(root), predictions_root=str(tmp_path / "predictions"))
    result = provider.get_slate("2026-08-11")
    assert result.source == "mock_dev_provider"
    assert result.retrieved_at  # non-empty ISO timestamp
    player = result.players_by_slate[result.slates[0].slate_id][0]
    assert player.source == "mock_dev_provider"
    assert player.external_player_id.startswith("mock-")
    assert player.retrieved_at == result.retrieved_at


def test_provider_player_and_slate_serialize_cleanly():
    player = ProviderPlayer(
        external_player_id="mock-1", name="X", team="AAA", opponent="BBB", game="AAA@BBB 7:05PM ET",
        salary=5000, position_eligibility=["OF"], slate_id="s1", slate_name="Main", start_time=None,
        source="mock_dev_provider", retrieved_at="2026-08-11T18:00:00+00:00",
    )
    slate = ProviderSlateInfo(slate_id="s1", slate_name="Main", site="draftkings", sport="MLB", start_time=None, game_count=1)
    result = ProviderSlateResult(slates=[slate], players_by_slate={"s1": [player]}, source="mock_dev_provider", retrieved_at="now")
    d = result.to_dict()
    assert d["slates"][0]["slate_id"] == "s1"
    assert d["players_by_slate"]["s1"][0]["name"] == "X"
