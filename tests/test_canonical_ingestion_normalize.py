"""M2C / M2M -- canonical normalization tests."""

import pytest

from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_UNRESOLVED, VALIDATION_STATE_REJECTED, VALIDATION_STATE_VALID
from canonical.schema_version import SLATE_NORMALIZED_V1
from canonical_ingestion.identity_bridge import build_name_team_index
from canonical_ingestion.normalize import NormalizationError, build_canonical_artifact
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo
from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE, UNOFFICIAL_DEVELOPMENT_SOURCE


def _slate_info(**overrides):
    base = dict(
        slate_id="dkunofficial-152904", slate_name="Main", site="draftkings", sport="MLB",
        start_time="2026-08-31T23:05:00Z", game_count=1, game_ids=["g1"], player_count=2,
        source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )
    base.update(overrides)
    return ProviderSlateInfo(**base)


def _player(external_id="999", name="Flex Player", team="BOS", start_time="2026-08-31T23:05:00Z", draftable_ids=None):
    return ProviderPlayer(
        external_player_id=external_id, name=name, team=team, opponent="TOR", game="TOR@BOS",
        salary=4500, position_eligibility=["1B", "OF"], slate_id="dkunofficial-152904", slate_name="Main",
        start_time=start_time, source="draftkings_unofficial", retrieved_at="2026-08-31T20:00:00Z",
        provider_draftable_ids=draftable_ids or ["101", "102"],
    )


def _index():
    return build_name_team_index({})


def test_schema_version_is_slate_normalized_v1():
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.schema_version == SLATE_NORMALIZED_V1


def test_slate_date_computed_from_earliest_game_start():
    players = [_player(external_id="1", start_time="2026-08-31T23:05:00Z"), _player(external_id="2", start_time="2026-08-31T19:05:00Z")]
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=players, internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.slate.slate_date == "2026-08-31"  # 19:05 UTC = 3:05pm ET
    assert artifact.slate.first_game_start_utc == "2026-08-31T19:05:00Z"


def test_no_game_start_instants_raises_normalization_error():
    player = _player(start_time=None)
    with pytest.raises(NormalizationError):
        build_canonical_artifact(
            sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
            provider_players=[player], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
        )


def test_provider_slate_id_preserved_verbatim_as_draftgroup():
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(slate_id="dkunofficial-152904"),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.slate.provider_slate_id == "dkunofficial-152904"
    assert artifact.slate.internal_slate_id == "uuid-1"
    assert artifact.slate.internal_slate_id != artifact.slate.provider_slate_id


def test_all_draftable_ids_preserved():
    player = _player(draftable_ids=["101", "102", "103"])
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=[player], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.players[0].provider_draftable_ids == ["101", "102", "103"]
    assert artifact.players[0].provider_player_id == "999"  # never collapsed into draftableId


def test_validation_state_valid_when_provenance_trusted():
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.slate.validation_state == VALIDATION_STATE_VALID


def test_validation_state_rejected_when_provenance_untrusted():
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(source_provenance=UNOFFICIAL_DEVELOPMENT_SOURCE),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert artifact.slate.validation_state == VALIDATION_STATE_REJECTED


def test_normalized_hash_deterministic_same_inputs():
    a = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
        fetched_at="2026-08-31T20:00:00Z",
    )
    b = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=[_player()], internal_slate_id="uuid-2", raw_hash="def", name_team_index=_index(),
        fetched_at="2026-08-31T21:30:00Z",
    )
    # Different internalSlateId/rawHash/fetchedAt (all volatile/identity
    # fields, excluded from the hash payload) -> same normalizedHash.
    assert a.normalized_hash == b.normalized_hash


def test_unresolved_identity_does_not_block_normalization():
    artifact = build_canonical_artifact(
        sport="MLB", site="draftkings", provider="draftkings_unofficial", slate_info=_slate_info(),
        provider_players=[_player()], internal_slate_id="uuid-1", raw_hash="abc", name_team_index=_index(),
    )
    assert len(artifact.players) == 1
    assert artifact.players[0].identity_status == IDENTITY_STATUS_UNRESOLVED
    assert artifact.players[0].internal_player_id is None
    assert artifact.slate.validation_state in (VALIDATION_STATE_VALID, VALIDATION_STATE_REJECTED)  # slate itself still valid/produced
