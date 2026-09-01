"""M3B / M3C / M3P -- automatic shadow promotion tests for
scripts/fetch_dfs_slate.py's in-process shadow ingestion + automatic
Postgres promotion trigger. No real network/subprocess calls -- every
external boundary (build_normalized_from_fetch, subprocess.run,
shutil.which) is monkeypatched.
"""

import subprocess

import pytest

import scripts.fetch_dfs_slate as fetch_dfs_slate
from canonical_ingestion.pipeline import ShadowIngestionResult


class _FakeSlateInfo:
    slate_id = "dkunofficial-146757"


class _FakeFetchResult:
    players_by_slate = {"dkunofficial-146757": ["player-1", "player-2"]}


def _ok_shadow_result(normalized_key="normalized/MLB/2026-09-01/draftkings_unofficial/dkunofficial-146757/x.json"):
    return ShadowIngestionResult(
        ok=True, provider_slate_id="dkunofficial-146757", internal_slate_id_proposed="uuid-1",
        raw_manifest_key="raw/x", raw_hash="rawhash", normalized_key=normalized_key, normalized_hash="normhash",
        is_semantic_duplicate=False, player_count=2, resolved_count=1, unresolved_count=1, review_required_count=0,
    )


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_scheduled_fetch_path_reaches_promotion_automatically(monkeypatch):
    # M3A/M3B: the scheduled worker path must reach promotion with NO
    # manual command -- proven here by confirming _run_canonical_promotion
    # is actually invoked as a direct consequence of a successful shadow
    # ingestion, with no human/manual step in between.
    import canonical_ingestion.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "build_normalized_from_fetch", lambda **kwargs: _ok_shadow_result())

    called = {}

    def fake_promotion(key):
        called["key"] = key
        return {"ok": True, "promoted": True}

    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", fake_promotion)

    status = fetch_dfs_slate._run_canonical_shadow_and_promotion(
        "2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object(),
    )
    assert called["key"] == "normalized/MLB/2026-09-01/draftkings_unofficial/dkunofficial-146757/x.json"
    assert status["promotion"] == {"ok": True, "promoted": True}
    assert status["ok"] is True


def test_shadow_failure_never_triggers_promotion(monkeypatch):
    import canonical_ingestion.pipeline as pipeline_module

    failed = ShadowIngestionResult(ok=False, provider_slate_id="dkunofficial-146757", error="boom", error_type="RuntimeError")
    monkeypatch.setattr(pipeline_module, "build_normalized_from_fetch", lambda **kwargs: failed)

    promotion_calls = []
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", lambda key: promotion_calls.append(key))

    status = fetch_dfs_slate._run_canonical_shadow_and_promotion(
        "2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object(),
    )
    assert promotion_calls == []
    assert status["promotion"] is None
    assert status["ok"] is False


def test_run_canonical_promotion_invokes_resolved_railway_ssh_with_correct_args(monkeypatch):
    captured = {}

    def fake_which(name):
        assert name == "railway"
        return r"C:\Users\bigro\AppData\Roaming\npm\railway.CMD"

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        captured["timeout"] = kwargs.get("timeout")
        return _FakeCompletedProcess(returncode=0, stdout='RESULT_JSON:{"promoted": true}')

    monkeypatch.setattr(fetch_dfs_slate.shutil, "which", fake_which)
    monkeypatch.setattr(fetch_dfs_slate.subprocess, "run", fake_run)

    result = fetch_dfs_slate._run_canonical_promotion("normalized/MLB/x.json")

    assert result["ok"] is True
    assert captured["argv"][0] == r"C:\Users\bigro\AppData\Roaming\npm\railway.CMD"
    assert captured["argv"][1:] == [
        "ssh", "--service", fetch_dfs_slate.CANONICAL_PROMOTION_RAILWAY_SERVICE,
        "--environment", fetch_dfs_slate.CANONICAL_PROMOTION_RAILWAY_ENVIRONMENT,
        "--", "npx", "tsx", "scripts/promote-canonical-slate.ts", "--key", "normalized/MLB/x.json",
    ]
    assert captured["cwd"] == fetch_dfs_slate.REPO_ROOT
    assert captured["timeout"] == fetch_dfs_slate.CANONICAL_PROMOTION_TIMEOUT_SECONDS


def test_run_canonical_promotion_reports_nonzero_exit_without_raising(monkeypatch):
    monkeypatch.setattr(fetch_dfs_slate.shutil, "which", lambda name: "/usr/bin/railway")
    monkeypatch.setattr(fetch_dfs_slate.subprocess, "run", lambda argv, **kwargs: _FakeCompletedProcess(returncode=1, stderr="boom"))

    result = fetch_dfs_slate._run_canonical_promotion("normalized/x.json")
    assert result["ok"] is False
    assert result["error_type"] == "promotion_script_nonzero_exit"


def test_run_canonical_promotion_missing_railway_cli_reported_not_raised(monkeypatch):
    monkeypatch.setattr(fetch_dfs_slate.shutil, "which", lambda name: None)
    result = fetch_dfs_slate._run_canonical_promotion("normalized/x.json")
    assert result["ok"] is False
    assert result["error_type"] == "railway_cli_not_found"


def test_run_canonical_promotion_subprocess_exception_never_propagates(monkeypatch):
    monkeypatch.setattr(fetch_dfs_slate.shutil, "which", lambda name: "/usr/bin/railway")

    def raise_timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=45)

    monkeypatch.setattr(fetch_dfs_slate.subprocess, "run", raise_timeout)
    result = fetch_dfs_slate._run_canonical_promotion("normalized/x.json")
    assert result["ok"] is False
    assert result["error_type"] == "TimeoutExpired"


def test_main_survives_an_unexpected_shadow_exception_and_still_wrote_legacy_artifact(monkeypatch, tmp_path):
    # M3C belt-and-suspenders, exercised through the REAL main() entry
    # point: even if _run_canonical_shadow_and_promotion raises something
    # totally unexpected, main() must still return normally (the
    # scheduled worker's exit code must not reflect a shadow bug) and
    # the legacy artifact it already wrote must be untouched.
    from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
    from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE

    slate = ProviderSlateInfo(
        slate_id="dkunofficial-1", slate_name="Main", site="draftkings", sport="MLB",
        start_time="2026-09-01T23:05:00Z", game_count=1, game_ids=["g1"], player_count=1,
        source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )
    player = ProviderPlayer(
        external_player_id="1", name="A", team="BOS", opponent="TOR", game="TOR@BOS", salary=4000,
        position_eligibility=["OF"], slate_id="dkunofficial-1", slate_name="Main",
        start_time="2026-09-01T23:05:00Z", source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z",
    )
    fake_result = ProviderSlateResult(slates=[slate], players_by_slate={"dkunofficial-1": [player]}, source="draftkings_unofficial", retrieved_at="2026-09-01T20:00:00Z")

    class FakeProvider:
        name = "draftkings_unofficial"

        def get_slate(self, *args, **kwargs):
            return fake_result

    monkeypatch.setattr(fetch_dfs_slate, "get_configured_provider", lambda date, **kwargs: (FakeProvider(), None, "explicit"))

    def raise_unexpected(*args, **kwargs):
        raise RuntimeError("unexpected shadow bug")
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_shadow_and_promotion", raise_unexpected)

    monkeypatch.setattr(
        "sys.argv",
        ["fetch_dfs_slate.py", "--date", "2026-09-01", "--slate-id", "dkunofficial-1", "--output-root", str(tmp_path)],
    )

    fetch_dfs_slate.main()  # must not raise

    written = list((tmp_path / "2026-09-01").glob("provider_slate_*.json"))
    assert len(written) == 1  # legacy artifact still written despite the shadow-path exception


def test_m3k_heartbeat_fires_only_when_promotion_actually_promoted(monkeypatch):
    import canonical_ingestion.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "build_normalized_from_fetch", lambda **kwargs: _ok_shadow_result())

    heartbeat_calls = []
    import canonical_ingestion.heartbeat as heartbeat_module
    monkeypatch.setattr(heartbeat_module, "send_success_heartbeat", lambda **kwargs: heartbeat_calls.append(kwargs))

    # Case 1: promotion script ran (ok=True) but did NOT actually
    # promote (a legitimate no-op/rejection) -- heartbeat must NOT fire.
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", lambda key: {"ok": True, "promoted": False, "reason": "semantic no-op"})
    fetch_dfs_slate._run_canonical_shadow_and_promotion("2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object())
    assert heartbeat_calls == []

    # Case 2: promotion script failed to even launch -- heartbeat must NOT fire.
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", lambda key: {"ok": False, "promoted": False, "error_type": "npx_not_found"})
    fetch_dfs_slate._run_canonical_shadow_and_promotion("2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object())
    assert heartbeat_calls == []

    # Case 3: real promotion -- heartbeat MUST fire, exactly once.
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", lambda key: {"ok": True, "promoted": True})
    fetch_dfs_slate._run_canonical_shadow_and_promotion("2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object())
    assert len(heartbeat_calls) == 1


def test_m3k_heartbeat_never_fires_when_shadow_ingestion_itself_failed(monkeypatch):
    import canonical_ingestion.pipeline as pipeline_module
    failed = ShadowIngestionResult(ok=False, provider_slate_id="dkunofficial-146757", error="boom", error_type="RuntimeError")
    monkeypatch.setattr(pipeline_module, "build_normalized_from_fetch", lambda **kwargs: failed)

    heartbeat_calls = []
    import canonical_ingestion.heartbeat as heartbeat_module
    monkeypatch.setattr(heartbeat_module, "send_success_heartbeat", lambda **kwargs: heartbeat_calls.append(kwargs))
    promotion_calls = []
    monkeypatch.setattr(fetch_dfs_slate, "_run_canonical_promotion", lambda key: promotion_calls.append(key))

    fetch_dfs_slate._run_canonical_shadow_and_promotion("2026-09-01", "MLB", "draftkings", _FakeSlateInfo(), _FakeFetchResult(), recorder=object())
    assert promotion_calls == []
    assert heartbeat_calls == []
