"""M1B / M1C / M1D -- canonical slate/slate-player/artifact model tests."""

import pytest

from canonical.models import (
    CanonicalSlate,
    CanonicalSlateArtifact,
    CanonicalSlatePlayer,
    IDENTITY_STATUS_RESOLVED,
    IDENTITY_STATUS_UNRESOLVED,
    VALIDATION_STATE_PENDING,
    slate_player_from_provider_player,
)
from canonical.schema_version import SLATE_NORMALIZED_V1
from dfs.providers.models import ProviderPlayer


def _slate(**overrides):
    base = dict(
        internal_slate_id="slate-uuid-1", sport="MLB", site="draftkings", provider="draftkings_unofficial",
        provider_slate_id="152904", slate_name="Main", slate_date="2026-08-31",
        first_game_start_utc="2026-08-31T23:05:00Z", game_count=8,
    )
    base.update(overrides)
    return CanonicalSlate(**base)


def test_canonical_slate_defaults_to_pending_validation():
    slate = _slate()
    assert slate.validation_state == VALIDATION_STATE_PENDING


def test_canonical_slate_rejects_invalid_validation_state():
    with pytest.raises(ValueError):
        _slate(validation_state="NOT_A_REAL_STATE")


def test_canonical_slate_provider_slate_id_is_not_internal_slate_id():
    slate = _slate(internal_slate_id="uuid-abc", provider_slate_id="152904")
    assert slate.internal_slate_id != slate.provider_slate_id


def test_slate_player_nullable_internal_player_id_accepted():
    player = CanonicalSlatePlayer(
        internal_slate_id="slate-uuid-1", provider_player_id="999", name="Flex Player",
        team="BOS", salary=4500, position_eligibility=["1B", "OF"],
        internal_player_id=None, identity_status=IDENTITY_STATUS_UNRESOLVED,
    )
    assert player.internal_player_id is None
    assert player.identity_status == IDENTITY_STATUS_UNRESOLVED


def test_slate_player_resolved_requires_internal_player_id():
    with pytest.raises(ValueError):
        CanonicalSlatePlayer(
            internal_slate_id="slate-uuid-1", provider_player_id="999", name="Flex Player",
            team="BOS", salary=4500, position_eligibility=["1B", "OF"],
            internal_player_id=None, identity_status=IDENTITY_STATUS_RESOLVED,
        )


def test_slate_player_multiple_draftable_ids_preserved():
    player = CanonicalSlatePlayer(
        internal_slate_id="slate-uuid-1", provider_player_id="999", name="Flex Player",
        team="BOS", salary=4500, position_eligibility=["1B", "OF"],
        provider_draftable_ids=["101", "102"],
    )
    assert player.provider_draftable_ids == ["101", "102"]
    assert player.provider_player_id == "999"  # draftableId never becomes canonical player id


def test_slate_player_from_provider_player_preserves_draftable_ids():
    provider_player = ProviderPlayer(
        external_player_id="999", name="Flex Player", team="BOS", opponent="TOR", game="TOR@BOS",
        salary=4500, position_eligibility=["1B", "OF"], slate_id="152904", slate_name="Main",
        start_time="2026-08-31T23:05:00Z", source="draftkings_unofficial", retrieved_at="2026-08-31T20:00:00Z",
        provider_draftable_ids=["101", "102"],
    )
    slate_player = slate_player_from_provider_player(provider_player, internal_slate_id="slate-uuid-1")
    assert slate_player.provider_draftable_ids == ["101", "102"]
    assert slate_player.provider_player_id == "999"
    assert slate_player.internal_player_id is None
    assert slate_player.identity_status == IDENTITY_STATUS_UNRESOLVED


def test_artifact_envelope_stores_hashes_once_not_per_player():
    slate = _slate()
    players = [
        CanonicalSlatePlayer(internal_slate_id=slate.internal_slate_id, provider_player_id="1", name="A", team="BOS", salary=4000, position_eligibility=["OF"]),
        CanonicalSlatePlayer(internal_slate_id=slate.internal_slate_id, provider_player_id="2", name="B", team="TOR", salary=5000, position_eligibility=["1B"]),
    ]
    artifact = CanonicalSlateArtifact(slate=slate, players=players, raw_hash="raw123", normalized_hash="norm456")
    payload = artifact.to_dict()
    assert payload["schemaVersion"] == SLATE_NORMALIZED_V1
    assert payload["rawHash"] == "raw123"
    assert payload["normalizedHash"] == "norm456"
    for player_dict in payload["players"]:
        assert "rawHash" not in player_dict
        assert "normalizedHash" not in player_dict
        assert "schemaVersion" not in player_dict
