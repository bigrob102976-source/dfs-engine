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
