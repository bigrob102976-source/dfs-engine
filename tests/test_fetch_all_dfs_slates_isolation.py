"""M3D -- multi-slate per-slate isolation tests for
scripts/fetch_all_dfs_slates.py: one hung/failing slate must never stop
the rest of the batch from being attempted."""

import subprocess

import scripts.fetch_all_dfs_slates as fetch_all


class _FakeSlate:
    def __init__(self, slate_id):
        self.slate_id = slate_id
        self.slate_name = "Main"


class _FakeDiscoveryResult:
    def __init__(self, slates):
        self.slates = slates


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_main(monkeypatch, slate_ids, run_side_effect):
    slates = [_FakeSlate(sid) for sid in slate_ids]
    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda date: (object(), None, "explicit"))
    fake_provider_result = _FakeDiscoveryResult(slates)

    class FakeProvider:
        def get_slate(self, *a, **k):
            return fake_provider_result

    monkeypatch.setattr(fetch_all, "get_configured_provider", lambda date: (FakeProvider(), None, "explicit"))
    monkeypatch.setattr(fetch_all.subprocess, "run", run_side_effect)
    # M4: this file's own scope is TODAY's per-slate isolation only --
    # tomorrow-prefetch has its own dedicated test file
    # (test_fetch_all_dfs_slates_tomorrow_prefetch.py). Stub it out here
    # so these tests never make a real network call.
    monkeypatch.setattr(fetch_all, "prefetch_future_slates", lambda **kwargs: {"date": "2026-09-02", "status": "NOT_YET_PUBLISHED", "slates": []})
    monkeypatch.setattr("sys.argv", ["fetch_all_dfs_slates.py", "--date", "2026-09-01"])


def test_one_timed_out_slate_does_not_stop_the_others(monkeypatch, capsys):
    calls = []

    def fake_run(argv, **kwargs):
        slate_id = argv[argv.index("--slate-id") + 1]
        calls.append(slate_id)
        if slate_id == "dkunofficial-2":
            raise subprocess.TimeoutExpired(cmd=argv, timeout=90)
        return _FakeProc(returncode=0, stdout="ok")

    _run_main(monkeypatch, ["dkunofficial-1", "dkunofficial-2", "dkunofficial-3"], fake_run)

    try:
        fetch_all.main()
    except SystemExit as exc:
        # exits 1 because one slate failed, but only AFTER attempting all three
        assert exc.code == 1

    # All three slates were attempted despite the middle one timing out.
    assert calls == ["dkunofficial-1", "dkunofficial-2", "dkunofficial-3"]


def test_one_launch_exception_does_not_stop_the_others(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        slate_id = argv[argv.index("--slate-id") + 1]
        calls.append(slate_id)
        if slate_id == "dkunofficial-1":
            raise OSError("could not launch subprocess")
        return _FakeProc(returncode=0, stdout="ok")

    _run_main(monkeypatch, ["dkunofficial-1", "dkunofficial-2"], fake_run)

    try:
        fetch_all.main()
    except SystemExit:
        pass

    assert calls == ["dkunofficial-1", "dkunofficial-2"]


def test_all_succeed_exits_cleanly(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeProc(returncode=0, stdout="ok")

    _run_main(monkeypatch, ["dkunofficial-1", "dkunofficial-2"], fake_run)
    fetch_all.main()  # must not raise/exit non-zero


def test_outer_timeout_kept_comfortably_above_inner_promotion_budget():
    import scripts.fetch_dfs_slate as fetch_dfs_slate

    # M3D: guards against a future edit accidentally narrowing the
    # safety margin between the outer per-slate timeout and the inner
    # promotion subprocess's own timeout (see both scripts' own comments).
    assert fetch_all.FETCH_TIMEOUT_SECONDS > fetch_dfs_slate.CANONICAL_PROMOTION_TIMEOUT_SECONDS + 15
