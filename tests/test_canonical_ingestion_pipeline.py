"""M2I / M2M -- shadow ingestion pipeline: failure isolation + semantic
duplicate handling, using LocalArtifactStorage rooted at a temp dir (so
these tests never touch the real repo's artifact tree) and a
monkeypatched DraftKingsUnofficialProvider.get_slate (no real network
call -- mirrors tests/test_dk_unofficial_provider.py's own convention)."""

import pytest

from canonical_ingestion import pipeline as pipeline_module
from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE
from research.artifact_storage import LocalArtifactStorage


def _fake_result():
    slate = ProviderSlateInfo(
        slate_id="dkunofficial-152904", slate_name="Main", site="draftkings", sport="MLB",
        start_time="2026-08-31T23:05:00Z", game_count=1, game_ids=["g1"], player_count=1,
        source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )
    player = ProviderPlayer(
        external_player_id="999", name="Flex Player", team="BOS", opponent="TOR", game="TOR@BOS",
        salary=4500, position_eligibility=["1B", "OF"], slate_id="dkunofficial-152904", slate_name="Main",
        start_time="2026-08-31T23:05:00Z", source="draftkings_unofficial", retrieved_at="2026-08-31T20:00:00Z",
        provider_draftable_ids=["101", "102"],
    )
    return ProviderSlateResult(slates=[slate], players_by_slate={"dkunofficial-152904": [player]}, source="draftkings_unofficial", retrieved_at="2026-08-31T20:00:00Z")


def _fake_get_slate(self, *args, **kwargs):
    # Simulates a real fetch actually firing the `capture` hook (see
    # draftkings_unofficial/client.py) so write_raw_capture has real
    # bytes to persist -- a fake that never calls capture would
    # correctly trigger EmptyRawCaptureError, which is exactly right for
    # a REAL unfetched call but wrong for this fake's intent.
    capture = kwargs.get("capture")
    if capture is not None:
        capture("https://api.draftkings.com/draftgroups/v1/draftgroups/152904/draftables", '{"draftables":[{"id":1}]}')
    return _fake_result()


@pytest.fixture
def patched_storage(tmp_path, monkeypatch):
    storage = LocalArtifactStorage(tmp_path)
    monkeypatch.setattr(pipeline_module, "resolve_artifact_storage", lambda root: storage)
    return storage


def test_successful_ingestion_reports_ok(monkeypatch, patched_storage):
    monkeypatch.setattr(DraftKingsUnofficialProvider, "get_slate", _fake_get_slate)
    monkeypatch.setattr(pipeline_module, "load_name_team_index", lambda: {})

    result = pipeline_module.ingest_slate_shadow(date="2026-08-31", provider_slate_id="dkunofficial-152904")
    assert result.ok is True
    assert result.player_count == 1
    assert result.unresolved_count == 1
    assert result.normalized_key is not None
    assert result.raw_manifest_key is not None


def test_failure_isolation_get_slate_raises_never_propagates(monkeypatch, patched_storage):
    def boom(self, *a, **k):
        raise RuntimeError("DraftKings is down")
    monkeypatch.setattr(DraftKingsUnofficialProvider, "get_slate", boom)

    result = pipeline_module.ingest_slate_shadow(date="2026-08-31", provider_slate_id="dkunofficial-152904")
    assert result.ok is False
    assert result.error_type == "RuntimeError"
    assert "DraftKings is down" in result.error  # visible, not swallowed


def test_slate_not_found_reported_not_raised(monkeypatch, patched_storage):
    monkeypatch.setattr(DraftKingsUnofficialProvider, "get_slate", _fake_get_slate)
    result = pipeline_module.ingest_slate_shadow(date="2026-08-31", provider_slate_id="dkunofficial-NOT-REAL")
    assert result.ok is False
    assert result.error_type == "slate_not_found"


def _fake_get_slate_chicago_eastern_mismatch(self, *args, **kwargs):
    # 2026-08-21T04:30:00Z = 00:30 ET on 2026-08-21 (already "tomorrow"
    # in Eastern) but still 23:30 CT on 2026-08-20 in Chicago -- the
    # same ~1-hour rollover window canonical/slate_date.py's own
    # test_eastern_chicago_one_hour_rollover_window covers at the pure
    # function level. Here the caller's own fetch-trigger `date` is
    # deliberately the CHICAGO-computed "2026-08-20" (what
    # fetch_dfs_slate.py's wrapper would pass near this exact window),
    # to prove RAW's own R2 namespace no longer follows it.
    slate = ProviderSlateInfo(
        slate_id="dkunofficial-999001", slate_name="Main", site="draftkings", sport="MLB",
        start_time="2026-08-21T04:30:00Z", game_count=1, game_ids=["g1"], player_count=1,
        source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )
    player = ProviderPlayer(
        external_player_id="1", name="Late Game Player", team="LAD", opponent="SD", game="SD@LAD",
        salary=4000, position_eligibility=["OF"], slate_id="dkunofficial-999001", slate_name="Main",
        start_time="2026-08-21T04:30:00Z", source="draftkings_unofficial", retrieved_at="2026-08-20T23:30:00Z",
    )
    capture = kwargs.get("capture")
    if capture is not None:
        capture("https://api.draftkings.com/draftgroups/v1/draftgroups/999001/draftables", '{"draftables":[{"id":1}]}')
    return ProviderSlateResult(slates=[slate], players_by_slate={"dkunofficial-999001": [player]}, source="draftkings_unofficial", retrieved_at="2026-08-20T23:30:00.000Z")


def test_m4a_raw_namespace_follows_eastern_slate_date_not_the_callers_chicago_date(monkeypatch, patched_storage):
    monkeypatch.setattr(DraftKingsUnofficialProvider, "get_slate", _fake_get_slate_chicago_eastern_mismatch)
    monkeypatch.setattr(pipeline_module, "load_name_team_index", lambda: {})

    # The caller passes "2026-08-20" -- its own Chicago-computed "today"
    # for this fetch-trigger window -- but the real first-game-start
    # instant is already 2026-08-21 in America/New_York.
    result = pipeline_module.ingest_slate_shadow(date="2026-08-20", provider_slate_id="dkunofficial-999001")

    assert result.ok is True
    assert "2026-08-21" in result.raw_manifest_key  # RAW follows the REAL Eastern slateDate
    assert "2026-08-20" not in result.raw_manifest_key  # never the caller's own Chicago-tainted date
    assert "2026-08-21" in result.normalized_key  # NORMALIZED already agreed before this fix -- still does


def test_repeated_ingestion_of_unchanged_slate_is_semantic_duplicate(monkeypatch, patched_storage):
    monkeypatch.setattr(DraftKingsUnofficialProvider, "get_slate", _fake_get_slate)
    monkeypatch.setattr(pipeline_module, "load_name_team_index", lambda: {})

    first = pipeline_module.ingest_slate_shadow(date="2026-08-31", provider_slate_id="dkunofficial-152904")
    second = pipeline_module.ingest_slate_shadow(date="2026-08-31", provider_slate_id="dkunofficial-152904")

    assert first.ok is True and second.ok is True
    assert first.normalized_hash == second.normalized_hash
    assert first.is_semantic_duplicate is False
    assert second.is_semantic_duplicate is True
    # Each ingestion still proposes its OWN internal_slate_id -- Postgres
    # (not this Python layer) is the actual stability authority, per
    # M2D's documented design (see canonical_ingestion/normalize.py).
    assert first.internal_slate_id_proposed != second.internal_slate_id_proposed
