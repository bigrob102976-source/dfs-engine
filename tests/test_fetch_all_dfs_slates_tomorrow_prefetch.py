"""M4B / M4C / M4D / M4F / M4G / M4L -- scripts/fetch_all_dfs_slates.py's
prefetch_future_slates(): shadow-only canonical acquisition of tomorrow's
(America/New_York) already-published real DK Classic slate(s). No real
network/subprocess calls -- DraftKingsUnofficialProvider.get_slate and
_run_canonical_promotion_batch are monkeypatched, mirroring
tests/test_fetch_dfs_slate_shadow.py's own convention for the shared
in-process shadow core.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import scripts.fetch_all_dfs_slates as fetch_all
from canonical_ingestion.pipeline import ShadowIngestionResult
from dfs.providers.base import ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE


def _tomorrow_eastern() -> str:
    return (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=1)).strftime("%Y-%m-%d")


def _slate(slate_id, name="Main"):
    return ProviderSlateInfo(
        slate_id=slate_id, slate_name=name, site="draftkings", sport="MLB",
        start_time="2026-09-02T23:05:00Z", game_count=1, game_ids=["g1"], player_count=1,
        source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )


def _player(slate_id, external_id="1"):
    return ProviderPlayer(
        external_player_id=external_id, name="A", team="BOS", opponent="TOR", game="TOR@BOS", salary=4000,
        position_eligibility=["OF"], slate_id=slate_id, slate_name="Main",
        start_time="2026-09-02T23:05:00Z", source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )


def _ok_shadow_result(normalized_key="normalized/MLB/2026-09-02/draftkings_unofficial/dkunofficial-1/x.json", normalized_hash="normhash-1"):
    return ShadowIngestionResult(
        ok=True, provider_slate_id="dkunofficial-1", internal_slate_id_proposed="uuid-1",
        raw_manifest_key="raw/x", raw_hash="rawhash", normalized_key=normalized_key, normalized_hash=normalized_hash,
        is_semantic_duplicate=False, player_count=1, resolved_count=0, unresolved_count=1, review_required_count=0,
    )


class FakeProvider:
    name = "draftkings_unofficial"

    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.calls = []

    def get_slate(self, date, **kwargs):
        self.calls.append((date, kwargs))
        if self._raises:
            raise self._raises
        return self._result


def test_tomorrow_uses_america_new_york_not_chicago(monkeypatch):
    # M4A/M4B: the date passed to get_slate() must be the REAL
    # America/New_York "tomorrow", independent of the machine's local
    # timezone or the legacy Chicago-anchored worker date.
    provider = FakeProvider(raises=ProviderNoSlateError("none yet"))
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    status = fetch_all.prefetch_future_slates()
    assert status["date"] == _tomorrow_eastern()
    assert provider.calls[0][0] == _tomorrow_eastern()


def test_absent_tomorrow_is_not_a_failure_and_creates_no_fake_slate(monkeypatch):
    provider = FakeProvider(raises=ProviderNoSlateError("DraftKings unofficial: no DraftGroups found"))
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    status = fetch_all.prefetch_future_slates()
    assert status["status"] == "NOT_YET_PUBLISHED"
    assert status["slates"] == []
    assert "error" not in status


def test_real_provider_error_reported_but_never_raises(monkeypatch):
    provider = FakeProvider(raises=ProviderUnavailableError("DK endpoint 500"))
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    status = fetch_all.prefetch_future_slates()  # must not raise
    assert status["status"] == "ERROR"
    assert "DK endpoint 500" in status["error"]


def test_multiple_classic_slates_all_discovered_and_promoted(monkeypatch):
    slates = [_slate("dkunofficial-1", "Main"), _slate("dkunofficial-2", "Turbo")]
    result = ProviderSlateResult(
        slates=slates,
        players_by_slate={"dkunofficial-1": [_player("dkunofficial-1")], "dkunofficial-2": [_player("dkunofficial-2")]},
        source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    provider = FakeProvider(result=result)
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    import canonical_ingestion.pipeline as pipeline_module
    build_calls = []

    def fake_build(**kwargs):
        build_calls.append(kwargs["slate_info"].slate_id)
        return _ok_shadow_result(normalized_key=f"normalized/MLB/x/{kwargs['slate_info'].slate_id}.json")

    monkeypatch.setattr(fetch_all, "build_normalized_from_fetch", fake_build)

    import scripts.fetch_dfs_slate as fetch_dfs_slate
    batch_calls = []

    def fake_batch(keys):
        batch_calls.append(list(keys))
        return [{"ok": True, "promoted": True} for _ in keys]

    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion_batch", fake_batch)

    status = fetch_all.prefetch_future_slates()
    assert status["status"] == "DISCOVERED"
    assert build_calls == ["dkunofficial-1", "dkunofficial-2"]
    assert len(batch_calls) == 1  # M4M: exactly ONE batch call for both slates, never one per slate
    assert len(batch_calls[0]) == 2
    assert all(s["ok"] for s in status["slates"])
    assert all(s["promotion"]["promoted"] for s in status["slates"])


def test_single_discovery_call_covers_every_slate(monkeypatch):
    # M4M: one discovery call must serve every accepted future slate --
    # never one discovery round trip per slate.
    slates = [_slate("dkunofficial-1", "Main"), _slate("dkunofficial-2", "Night")]
    result = ProviderSlateResult(
        slates=slates,
        players_by_slate={"dkunofficial-1": [_player("dkunofficial-1")], "dkunofficial-2": [_player("dkunofficial-2")]},
        source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    provider = FakeProvider(result=result)
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)
    monkeypatch.setattr(fetch_all, "build_normalized_from_fetch", lambda **kwargs: _ok_shadow_result())

    import scripts.fetch_dfs_slate as fetch_dfs_slate
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion_batch", lambda keys: [{"ok": True, "promoted": True} for _ in keys])

    fetch_all.prefetch_future_slates()
    assert len(provider.calls) == 1


def test_a_shadow_failure_on_one_slate_does_not_stop_the_others(monkeypatch):
    slates = [_slate("dkunofficial-1", "Main"), _slate("dkunofficial-2", "Turbo")]
    result = ProviderSlateResult(
        slates=slates,
        players_by_slate={"dkunofficial-1": [_player("dkunofficial-1")], "dkunofficial-2": [_player("dkunofficial-2")]},
        source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    provider = FakeProvider(result=result)
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    def fake_build(**kwargs):
        if kwargs["slate_info"].slate_id == "dkunofficial-1":
            return ShadowIngestionResult(ok=False, provider_slate_id="dkunofficial-1", error="boom", error_type="RuntimeError")
        return _ok_shadow_result()

    monkeypatch.setattr(fetch_all, "build_normalized_from_fetch", fake_build)
    import scripts.fetch_dfs_slate as fetch_dfs_slate
    promoted_keys = []

    def fake_batch(keys):
        promoted_keys.extend(keys)
        return [{"ok": True, "promoted": True} for _ in keys]

    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion_batch", fake_batch)

    status = fetch_all.prefetch_future_slates()
    assert len(status["slates"]) == 2
    assert status["slates"][0]["ok"] is False
    assert status["slates"][1]["ok"] is True
    assert promoted_keys == ["normalized/MLB/2026-09-02/draftkings_unofficial/dkunofficial-1/x.json"]  # only the successful one promoted


def test_semantic_duplicate_on_repeat_prefetch_reported_not_treated_as_error(monkeypatch):
    slates = [_slate("dkunofficial-1", "Main")]
    result = ProviderSlateResult(
        slates=slates, players_by_slate={"dkunofficial-1": [_player("dkunofficial-1")]},
        source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    provider = FakeProvider(result=result)
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    dup_result = ShadowIngestionResult(
        ok=True, provider_slate_id="dkunofficial-1", internal_slate_id_proposed="uuid-1",
        raw_manifest_key="raw/x", raw_hash="rawhash", normalized_key="normalized/x.json", normalized_hash="normhash-1",
        is_semantic_duplicate=True, player_count=1, resolved_count=0, unresolved_count=1, review_required_count=0,
    )
    monkeypatch.setattr(fetch_all, "build_normalized_from_fetch", lambda **kwargs: dup_result)
    import scripts.fetch_dfs_slate as fetch_dfs_slate
    monkeypatch.setattr(
        fetch_dfs_slate, "_run_canonical_promotion_batch",
        lambda keys: [{"ok": False, "promoted": False, "reason": "identical normalizedHash -- semantic no-op."} for _ in keys],
    )

    status = fetch_all.prefetch_future_slates()
    assert status["slates"][0]["is_semantic_duplicate"] is True
    assert status["slates"][0]["promotion"]["promoted"] is False
    assert status["status"] == "DISCOVERED"  # a no-op is still a healthy cycle, not an error


def test_m4m_multiple_future_slates_promoted_in_one_ssh_round_trip_not_one_per_slate(monkeypatch):
    # M4M: this is the exact scenario a live natural worker cycle showed
    # pushing total runtime past the internal timeout -- several real
    # Classic slates for the same date, each previously requiring its
    # own separate `railway ssh` subprocess launch.
    slates = [_slate("dkunofficial-1", "Main"), _slate("dkunofficial-2", "Turbo"), _slate("dkunofficial-3", "Night")]
    result = ProviderSlateResult(
        slates=slates,
        players_by_slate={sid: [_player(sid)] for sid in ["dkunofficial-1", "dkunofficial-2", "dkunofficial-3"]},
        source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    provider = FakeProvider(result=result)
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)
    monkeypatch.setattr(
        fetch_all, "build_normalized_from_fetch",
        lambda **kwargs: _ok_shadow_result(normalized_key=f"normalized/MLB/x/{kwargs['slate_info'].slate_id}.json"),
    )

    import scripts.fetch_dfs_slate as fetch_dfs_slate
    batch_calls = []

    def fake_batch(keys):
        batch_calls.append(list(keys))
        return [{"ok": True, "promoted": True} for _ in keys]

    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion_batch", fake_batch)

    status = fetch_all.prefetch_future_slates()
    assert len(batch_calls) == 1  # ONE ssh round trip total, not 3
    assert len(batch_calls[0]) == 3
    assert all(s["promotion"]["promoted"] for s in status["slates"])


def test_uses_a_fresh_unshared_cache_and_direct_provider_never_get_configured_provider(monkeypatch):
    # M4D: tomorrow-prefetch must always use the real live provider
    # directly, bypassing DFS_SALARY_PROVIDER/Mock Mode -- confirmed by
    # asserting get_configured_provider is never even called.
    called = []
    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda *a, **k: called.append(1))

    provider = FakeProvider(raises=ProviderNoSlateError("none yet"))
    monkeypatch.setattr(fetch_all, "DraftKingsUnofficialProvider", lambda: provider)

    fetch_all.prefetch_future_slates()
    assert called == []
    assert "cache" in provider.calls[0][1]
    assert "capture" in provider.calls[0][1]


def test_main_reaches_tomorrow_prefetch_after_today_with_no_slates(monkeypatch, capsys):
    # M4J-adjacent: today succeeding with nothing to fetch must not skip tomorrow.
    empty_result = ProviderSlateResult(slates=[], players_by_slate={}, source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z")
    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda date: (FakeProvider(result=empty_result), None, "explicit"))
    tomorrow_calls = []
    monkeypatch.setattr(fetch_all, "prefetch_future_slates", lambda **kwargs: tomorrow_calls.append(1) or {"date": "2026-09-02", "status": "NOT_YET_PUBLISHED", "slates": []})
    monkeypatch.setattr("sys.argv", ["fetch_all_dfs_slates.py", "--date", "2026-09-01"])

    fetch_all.main()  # must not raise -- today had nothing, tomorrow still attempted
    assert tomorrow_calls == [1]
    assert "TOMORROW PREFETCH" in capsys.readouterr().out


def test_main_reaches_tomorrow_prefetch_even_when_today_fails(monkeypatch, capsys):
    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda date: (None, "no provider configured", "unconfigured"))
    tomorrow_calls = []
    monkeypatch.setattr(fetch_all, "prefetch_future_slates", lambda **kwargs: tomorrow_calls.append(1) or {"date": "2026-09-02", "status": "NOT_YET_PUBLISHED", "slates": []})
    monkeypatch.setattr("sys.argv", ["fetch_all_dfs_slates.py", "--date", "2026-09-01"])

    with pytest.raises(SystemExit) as exc_info:
        fetch_all.main()
    assert exc_info.value.code == 1  # today's own failure exit code is preserved
    assert tomorrow_calls == [1]  # but tomorrow was still attempted first


def test_a_tomorrow_prefetch_exception_never_changes_todays_exit_code(monkeypatch):
    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda date: (None, "no provider configured", "unconfigured"))

    def raise_unexpected(**kwargs):
        raise RuntimeError("unexpected tomorrow bug")
    monkeypatch.setattr(fetch_all, "prefetch_future_slates", raise_unexpected)
    monkeypatch.setattr("sys.argv", ["fetch_all_dfs_slates.py", "--date", "2026-09-01"])

    with pytest.raises(SystemExit) as exc_info:
        fetch_all.main()
    assert exc_info.value.code == 1  # unchanged: today's own failure, not tomorrow's exception
