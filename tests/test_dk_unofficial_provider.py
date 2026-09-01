"""Tests for DraftKingsUnofficialProvider -- Milestone M1: this is the
permanent DEFAULT DraftKings slate source, reachable automatically via
the production cascade with no override required. DK_UNOFFICIAL_ENABLED
is now an explicit operational kill switch (not an opt-in gate): the
safety-critical piece is that setting it to an explicit "off" value
disables the provider without making any network call, while leaving it
unset (the normal state) does not disable anything."""

import pytest

from dfs.providers.base import ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE, TRUSTED_FOR_PRODUCTION, UNOFFICIAL_DEVELOPMENT_SOURCE
from draftkings_unofficial import collector
from draftkings_unofficial.models import DkContest, DkRosterRules, DkRosterSlot, DkSlate, DkSlateGame, DkDraftable, DkTeam

# Milestone 32.2B: DraftKingsUnofficialProvider now runs structural
# validation (correct game type / roster template / salary cap -- see
# draftkings_unofficial/structural_validation.py) before including a
# DraftGroup, so any fixture that expects a slate to actually be
# returned needs a matching Classic contest + valid roster rules.
_CLASSIC_CONTEST = DkContest(
    contest_id=1, name="Test Classic Contest", sport_id=2, draft_group_id=10,
    game_type="Classic", game_type_id=2, start_time_raw=None, start_time_iso=None,
)
_VALID_ROSTER_SLOTS = [
    DkRosterSlot(roster_slot_id=110, name="P"), DkRosterSlot(roster_slot_id=110, name="P"),
    DkRosterSlot(roster_slot_id=111, name="C"), DkRosterSlot(roster_slot_id=112, name="1B"),
    DkRosterSlot(roster_slot_id=113, name="2B"), DkRosterSlot(roster_slot_id=114, name="3B"),
    DkRosterSlot(roster_slot_id=115, name="SS"), DkRosterSlot(roster_slot_id=116, name="OF"),
    DkRosterSlot(roster_slot_id=116, name="OF"), DkRosterSlot(roster_slot_id=116, name="OF"),
]
_VALID_ROSTER_RULES = DkRosterRules(
    game_type_id=2, sport_id=2, name="Classic", draft_type="SalaryCap",
    salary_cap_enabled=True, salary_cap=50000, roster_slots=_VALID_ROSTER_SLOTS,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DK_UNOFFICIAL_ENABLED", raising=False)
    monkeypatch.delenv("DFS_SALARY_PROVIDER", raising=False)


def test_is_enabled_true_by_default():
    from dfs.providers.draftkings_unofficial_provider import is_enabled
    assert is_enabled() is True


def test_is_enabled_true_variants(monkeypatch):
    # Kept enabled by any value that isn't an explicit "off" -- these are
    # all no-ops relative to the (now-enabled) default, but must not
    # accidentally disable the provider.
    from dfs.providers.draftkings_unofficial_provider import is_enabled
    for value in ("true", "True", "TRUE", "1", "yes"):
        monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", value)
        assert is_enabled() is True


def test_is_enabled_false_variants(monkeypatch):
    # The explicit operational kill switch -- only these values disable it.
    from dfs.providers.draftkings_unofficial_provider import is_enabled
    for value in ("false", "False", "FALSE", "0", "no", "No"):
        monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", value)
        assert is_enabled() is False


def test_is_enabled_true_when_unset_or_empty():
    from dfs.providers.draftkings_unofficial_provider import is_enabled
    assert is_enabled() is True  # DK_UNOFFICIAL_ENABLED unset (_clean_env fixture)


def test_disabled_provider_raises_without_any_network_call(monkeypatch):
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    def fail_if_called(*a, **k):
        raise AssertionError("collector.collect_sport_universe must not be called when disabled")
    monkeypatch.setattr(collector, "collect_sport_universe", fail_if_called)

    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "false")  # explicit kill switch
    provider = DraftKingsUnofficialProvider()
    with pytest.raises(ProviderUnavailableError, match="disabled"):
        provider.get_slate("2026-08-20", sport="MLB")


def test_enabled_provider_is_the_automatic_cascade_default(monkeypatch):
    # Milestone M1: with no DFS_SALARY_PROVIDER override and Mock Mode
    # off, the automatic cascade must resolve to DraftKings Unofficial
    # by default -- no env var required.
    import dfs.providers.config as config_module
    from dfs.providers.config import get_configured_provider

    monkeypatch.setattr(config_module, "is_mock_mode_enabled", lambda: False)
    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)
    monkeypatch.setattr(collector, "collect_slate_detail", lambda *a, **k: _detail_ok())

    provider, reason, source = get_configured_provider("2026-08-20")
    assert provider is not None
    assert provider.name == "draftkings_unofficial"
    assert source == "draftkings_unofficial_live"
    assert reason is None


def test_registered_for_explicit_override(monkeypatch):
    from dfs.providers.config import PROVIDER_FACTORIES
    assert "draftkings_unofficial" in PROVIDER_FACTORIES


def test_explicit_override_still_respects_kill_switch(monkeypatch):
    # Even via the explicit DFS_SALARY_PROVIDER override, the operational
    # kill switch must still be honored -- it's a safety valve, not
    # bypassable by naming the provider directly.
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "draftkings_unofficial")
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "false")
    from dfs.providers.config import get_configured_provider

    provider, reason, source = get_configured_provider("2026-08-20")
    assert source == "explicit"
    assert provider is not None
    with pytest.raises(ProviderUnavailableError, match="disabled"):
        provider.get_slate("2026-08-20", sport="MLB")


def test_explicit_override_works_without_any_flag(monkeypatch):
    # Milestone M1: explicitly naming the provider must work out of the
    # box, with no DK_UNOFFICIAL_ENABLED needed (default is enabled).
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "draftkings_unofficial")
    from dfs.providers.config import get_configured_provider

    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)
    monkeypatch.setattr(collector, "collect_slate_detail", lambda *a, **k: _detail_ok())

    provider, reason, source = get_configured_provider("2026-08-20")
    assert source == "explicit"
    assert provider is not None
    result = provider.get_slate("2026-08-20", sport="MLB")
    assert len(result.slates) == 1


def _slate(dg_id=10, game_type_id=2):
    return DkSlate(draft_group_id=dg_id, sport_id=2, sport_code="MLB", game_type_id=game_type_id,
                   game_type_name="Classic", start_time="2026-08-20T18:00:00Z",
                   tag="Featured", label=None, contest_ids=[1],
                   raw={"StartDateEst": "2026-08-20T18:00:00.0000000"})


def _detail_ok():
    game = DkSlateGame(competition_id=100, sport_id=2, name="TOR @ BOS", start_time="2026-08-20T18:00:00Z",
                        home_team=DkTeam(team_id=1, abbreviation="BOS"), away_team=DkTeam(team_id=2, abbreviation="TOR"))
    draftable = DkDraftable(draftable_id=1, draft_group_id=10, player_id=1, player_dk_id=1, display_name="A",
                             first_name=None, last_name=None, position="OF", roster_slot_id=1, salary=4000,
                             status="None", team_id=1, team_abbreviation="BOS", competition_id=100)
    return collector.SlateDetailResult(status=collector.STATUS_OK, draft_group_id=10, games=[game], draftables=[draftable], roster_rules=_VALID_ROSTER_RULES)


def test_enabled_provider_builds_provider_slate_result(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)
    monkeypatch.setattr(collector, "collect_slate_detail", lambda *a, **k: _detail_ok())

    provider = DraftKingsUnofficialProvider()
    result = provider.get_slate("2026-08-20", sport="MLB")
    assert len(result.slates) == 1
    # Milestone 32.2B: structural validation passes (Classic game type +
    # valid roster template/salary cap) -> the upgraded provenance claim,
    # not the generic "unverified" one.
    assert result.slates[0].source_provenance == DRAFTKINGS_UNOFFICIAL_LIVE
    # Milestone 32.2B architecture decision: DRAFTKINGS_UNOFFICIAL_LIVE
    # (structural + content validation both passed) IS trusted for
    # production -- this is the sole DK slate source going forward, no
    # manual CSV step. The bare, unvalidated UNOFFICIAL_DEVELOPMENT_SOURCE
    # claim remains untrusted.
    assert DRAFTKINGS_UNOFFICIAL_LIVE in TRUSTED_FOR_PRODUCTION
    assert UNOFFICIAL_DEVELOPMENT_SOURCE not in TRUSTED_FOR_PRODUCTION
    players = result.players_by_slate[result.slates[0].slate_id]
    assert len(players) == 1
    assert players[0].name == "A"
    assert players[0].opponent == "TOR"


# 2026-09-01 disk incident: the scheduled production worker's ONE call
# path (this provider's get_slate()) must default the local raw archive
# OFF, since it grew unbounded to 27.31 GB in 12 days -- R2 is now the
# real durable RAW record (canonical_ingestion/raw_capture.py, M2).


def _wire_universe_and_detail(monkeypatch, captured_kwargs):
    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])

    def fake_universe(sport_code, **kwargs):
        captured_kwargs["universe"] = kwargs
        return universe

    def fake_detail(*args, **kwargs):
        captured_kwargs["detail"] = kwargs
        return _detail_ok()

    monkeypatch.setattr(collector, "collect_sport_universe", fake_universe)
    monkeypatch.setattr(collector, "collect_slate_detail", fake_detail)


def test_scheduled_worker_path_disables_local_raw_archive_by_default(monkeypatch):
    monkeypatch.delenv("DK_UNOFFICIAL_LOCAL_RAW_ARCHIVE_ENABLED", raising=False)
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    captured: dict = {}
    _wire_universe_and_detail(monkeypatch, captured)

    DraftKingsUnofficialProvider().get_slate("2026-08-20", sport="MLB")

    assert captured["universe"]["save_snapshot"] is False
    assert captured["detail"]["save_snapshot"] is False


def test_local_raw_archive_can_still_be_enabled_explicitly_for_development(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_LOCAL_RAW_ARCHIVE_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    captured: dict = {}
    _wire_universe_and_detail(monkeypatch, captured)

    DraftKingsUnofficialProvider().get_slate("2026-08-20", sport="MLB")

    assert captured["universe"]["save_snapshot"] is True
    assert captured["detail"]["save_snapshot"] is True


def test_disabling_local_raw_archive_does_not_affect_r2_persistence(monkeypatch):
    # Structural proof, not just behavioral: draftkings_unofficial/collector.py
    # (the module save_snapshot controls) never imports the R2/object-storage
    # abstraction at all -- disabling local disk archiving cannot, even in
    # principle, touch R2. research/artifact_storage.py-based persistence
    # (the REAL durable RAW/NORMALIZED record, plus the pre-existing
    # provider_slate_*.json artifact) lives in an entirely separate module
    # this provider's get_slate() never imports either.
    import ast
    import inspect

    import draftkings_unofficial.collector as collector_module
    import dfs.providers.draftkings_unofficial_provider as provider_module

    for module in (collector_module, provider_module):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
        assert not any("artifact_storage" in name for name in imported_names), f"{module.__name__} must never import research.artifact_storage"


def _detail_with_multi_slot_player():
    """M32.2B live finding: DraftKings' draftables endpoint returns one
    row per player PER ROSTER-SLOT ELIGIBILITY -- confirmed live for
    DraftGroup 152543 (Shohei Ohtani, player_id 727378, two rows:
    rosterSlotId 112 and 116, both position "1B/OF"). This fixture
    mirrors that shape with two different positions to also prove
    eligibility is unioned, not just deduped."""
    game = DkSlateGame(competition_id=100, sport_id=2, name="TOR @ BOS", start_time="2026-08-20T18:00:00Z",
                        home_team=DkTeam(team_id=1, abbreviation="BOS"), away_team=DkTeam(team_id=2, abbreviation="TOR"))
    row_a = DkDraftable(draftable_id=101, draft_group_id=10, player_id=999, player_dk_id=999, display_name="Flex Player",
                         first_name=None, last_name=None, position="1B", roster_slot_id=112, salary=4500,
                         status="None", team_id=1, team_abbreviation="BOS", competition_id=100)
    row_b = DkDraftable(draftable_id=102, draft_group_id=10, player_id=999, player_dk_id=999, display_name="Flex Player",
                         first_name=None, last_name=None, position="OF", roster_slot_id=116, salary=4500,
                         status="None", team_id=1, team_abbreviation="BOS", competition_id=100)
    other = DkDraftable(draftable_id=201, draft_group_id=10, player_id=555, player_dk_id=555, display_name="Other Player",
                         first_name=None, last_name=None, position="SS", roster_slot_id=113, salary=3800,
                         status="None", team_id=2, team_abbreviation="TOR", competition_id=100)
    return collector.SlateDetailResult(status=collector.STATUS_OK, draft_group_id=10, games=[game], draftables=[row_a, row_b, other], roster_rules=_VALID_ROSTER_RULES)


def test_multi_roster_slot_rows_for_the_same_player_are_merged_not_duplicated(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)
    monkeypatch.setattr(collector, "collect_slate_detail", lambda *a, **k: _detail_with_multi_slot_player())

    provider = DraftKingsUnofficialProvider()
    result = provider.get_slate("2026-08-20", sport="MLB")
    players = result.players_by_slate[result.slates[0].slate_id]

    # 3 raw draftable rows, 2 real players -- must produce exactly 2 ProviderPlayer entries.
    assert len(players) == 2
    flex_player = next(p for p in players if p.name == "Flex Player")
    assert flex_player.external_player_id == "999"  # DK's stable player_id, never the per-roster-slot draftableId
    assert flex_player.position_eligibility == ["1B", "OF"]  # unioned across both raw rows, order preserved

    # slates[0].player_count must reflect the deduped list actually
    # returned, not DraftKings' raw 3-row draftable count.
    assert result.slates[0].player_count == 2


def test_multi_roster_slot_rows_preserve_all_draftable_ids(monkeypatch):
    # M1D: draftableId must be preserved (never discarded, never used as
    # identity) even though rows sharing one player_id are merged into a
    # single ProviderPlayer.
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()], contests=[_CLASSIC_CONTEST])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)
    monkeypatch.setattr(collector, "collect_slate_detail", lambda *a, **k: _detail_with_multi_slot_player())

    provider = DraftKingsUnofficialProvider()
    result = provider.get_slate("2026-08-20", sport="MLB")
    players = result.players_by_slate[result.slates[0].slate_id]

    flex_player = next(p for p in players if p.name == "Flex Player")
    other_player = next(p for p in players if p.name == "Other Player")
    assert flex_player.provider_draftable_ids == ["101", "102"]
    assert flex_player.external_player_id == "999"  # draftableId never becomes the identity
    assert other_player.provider_draftable_ids == ["201"]


def test_no_active_slate_raises_provider_no_slate_error(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_NO_ACTIVE_SLATE, sport_code="NHL")
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)

    provider = DraftKingsUnofficialProvider()
    with pytest.raises(ProviderNoSlateError):
        provider.get_slate("2026-08-20", sport="NHL")


def test_no_slates_matching_requested_date_raises_no_slate_error(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_OK, sport_code="MLB", slates=[_slate()])
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)

    provider = DraftKingsUnofficialProvider()
    with pytest.raises(ProviderNoSlateError):
        provider.get_slate("2099-01-01", sport="MLB")  # slate's date doesn't match


def test_universe_error_status_raises_provider_unavailable(monkeypatch):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider

    universe = collector.SportUniverseResult(status=collector.STATUS_UNAVAILABLE, sport_code="MLB", error="down")
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)

    provider = DraftKingsUnofficialProvider()
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-20", sport="MLB")


def test_config_surfaces_real_failure_without_csv_or_mock_fallback(monkeypatch):
    """Milestone M1: when the REAL DraftKingsUnofficialProvider fails
    (e.g. contest discovery is down), the automatic cascade must surface
    that failure directly. CSV providers must never even be attempted
    (they're no longer part of the automatic path at all), and mock is
    never used as a fallback triggered by this failure."""
    from dfs.providers.config import get_configured_provider, NO_PROVIDER_CONFIGURED_MESSAGE
    import dfs.providers.config as config_module

    monkeypatch.setattr(config_module, "is_mock_mode_enabled", lambda: False)

    csv_calls = []

    class _NeverCalledCsv:
        def get_slate(self, *a, **k):
            csv_calls.append(1)
            raise ProviderUnavailableError("should never be reached")

    monkeypatch.setattr(config_module, "DraftKingsCsvProvider", _NeverCalledCsv)
    monkeypatch.setattr(config_module, "CsvImportPoolProvider", _NeverCalledCsv)

    universe = collector.SportUniverseResult(status=collector.STATUS_UNAVAILABLE, sport_code="MLB", error="down")
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code, **k: universe)

    provider, reason, source = get_configured_provider("2026-08-20")
    assert provider is None
    assert NO_PROVIDER_CONFIGURED_MESSAGE in reason
    assert "down" in reason
    assert source == "unconfigured"
    assert csv_calls == []  # CSV providers must never even be attempted


def test_config_mock_mode_wins_over_draftkings_unofficial_without_touching_it(monkeypatch):
    """Mock Mode is checked before DraftKings Unofficial is even
    attempted -- its outcome must never depend on whether DraftKings
    Unofficial would have succeeded (that would make mock a fallback
    triggered by a live-provider failure, which Milestone M1 forbids)."""
    from dfs.providers.config import get_configured_provider
    import dfs.providers.config as config_module

    monkeypatch.setattr(config_module, "is_mock_mode_enabled", lambda: True)

    def fail_if_called(*a, **k):
        raise AssertionError("DraftKings Unofficial must not be attempted when Mock Mode is on")
    monkeypatch.setattr(collector, "collect_sport_universe", fail_if_called)

    provider, reason, source = get_configured_provider("2026-08-20")
    assert provider is not None
    assert provider.name == "mock_dev_provider"
    assert source == "mock_explicit"
