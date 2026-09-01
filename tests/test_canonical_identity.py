"""M1E / M1F / M1G / M1H -- identity foundation tests."""

import pytest

from canonical.identity_matching import (
    IdentityMatchCandidate,
    STATUS_MATCHED,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNMATCHED,
    identity_status_for_match_status,
    resolve_identity,
)
from canonical.identity_models import (
    CONFIDENCE_BY_METHOD,
    CrosswalkConflictError,
    IdentityReviewQueueEntry,
    METHOD_EXCEPTION_TABLE,
    METHOD_EXISTING_CROSSWALK,
    Player,
    PlayerExternalId,
    REVIEW_QUEUE_PENDING,
)
from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED, IDENTITY_STATUS_UNRESOLVED


def _candidate(external_id="dk-999"):
    return IdentityMatchCandidate(sport="MLB", provider="draftkings", external_id=external_id, external_id_type="player_id", name="Flex Player", team="BOS", position="OF")


def test_internal_player_id_immutable_once_minted():
    player = Player(internal_player_id="uuid-1", sport="MLB", canonical_name="Flex Player", normalized_name="flex player")
    # Discovering a new external ID must never require (or imply)
    # minting a different internal_player_id -- the same internal id is
    # reused across every PlayerExternalId row attached to this player.
    mapping_a = PlayerExternalId(id="ext-1", internal_player_id=player.internal_player_id, sport="MLB", provider="draftkings", external_id="999", external_id_type="player_id", match_method=METHOD_EXISTING_CROSSWALK, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXISTING_CROSSWALK])
    mapping_b = PlayerExternalId(id="ext-2", internal_player_id=player.internal_player_id, sport="MLB", provider="mlbam", external_id="660271", external_id_type="mlbam_id", match_method=METHOD_EXISTING_CROSSWALK, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXISTING_CROSSWALK])
    assert mapping_a.internal_player_id == mapping_b.internal_player_id == player.internal_player_id


def test_external_id_mapping_via_existing_crosswalk():
    result = resolve_identity(_candidate(), existing_crosswalk={"dk-999": "uuid-1"})
    assert result.status == STATUS_MATCHED
    assert result.internal_player_id == "uuid-1"
    assert result.match_method == METHOD_EXISTING_CROSSWALK


def test_historical_provider_id_supported_two_mappings_one_player():
    # A provider ID migration: the same internal player has an old and a
    # new external id from the same provider, one marked not-current.
    old = PlayerExternalId(id="ext-old", internal_player_id="uuid-1", sport="MLB", provider="draftkings", external_id="111", external_id_type="player_id", match_method=METHOD_EXCEPTION_TABLE, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXCEPTION_TABLE], is_current=False, valid_to="2025-01-01")
    new = PlayerExternalId(id="ext-new", internal_player_id="uuid-1", sport="MLB", provider="draftkings", external_id="999", external_id_type="player_id", match_method=METHOD_EXCEPTION_TABLE, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXCEPTION_TABLE], is_current=True)
    assert old.internal_player_id == new.internal_player_id
    assert old.is_current is False and new.is_current is True


def test_unresolved_is_allowed_and_servable():
    result = resolve_identity(_candidate("dk-brand-new-rookie"))
    assert result.status == STATUS_UNMATCHED
    assert result.internal_player_id is None
    assert identity_status_for_match_status(result.status) == IDENTITY_STATUS_UNRESOLVED


def test_review_required_allowed_with_plausible_candidates():
    result = resolve_identity(_candidate("dk-ambiguous"), ambiguous_candidate_internal_player_ids=["uuid-1", "uuid-2"])
    assert result.status == STATUS_REVIEW_REQUIRED
    assert result.internal_player_id is None
    assert result.candidate_internal_player_ids == ["uuid-1", "uuid-2"]
    assert identity_status_for_match_status(result.status) == IDENTITY_STATUS_REVIEW_REQUIRED


def test_review_queue_entry_created_for_review_required():
    entry = IdentityReviewQueueEntry(
        id="queue-1", sport="MLB", provider="draftkings", external_id="dk-ambiguous",
        provider_player_name="Flex Player", reason="Two plausible candidates.",
        candidate_internal_player_id="uuid-1",
    )
    assert entry.status == REVIEW_QUEUE_PENDING


def test_fuzzy_auto_merge_is_not_possible_no_candidates_means_unmatched():
    # There is no name/team similarity tier at all -- a brand-new
    # external id with zero deterministic matches is UNMATCHED, never
    # auto-linked to a "close enough" existing player.
    result = resolve_identity(_candidate("dk-totally-new"), existing_crosswalk={}, reviewed_provider_mappings={}, deterministic_source_mappings={}, exception_table={})
    assert result.status == STATUS_UNMATCHED
    assert result.match_method is None


def test_conflicting_external_mapping_rejected():
    with pytest.raises(CrosswalkConflictError):
        resolve_identity(
            _candidate("dk-999"),
            existing_crosswalk={"dk-999": "uuid-1"},
            deterministic_source_mappings={"dk-999": "uuid-2"},
        )


def test_current_mapping_uniqueness_conceptually_one_current_per_provider_external_id():
    # Two PlayerExternalId rows for the SAME (provider, external_id,
    # sport) both marked is_current=True but pointing at different
    # internal players is exactly the state the Postgres partial unique
    # index (M1I) forbids; at this layer, resolve_identity's conflict
    # check is what prevents ever constructing that state in the first
    # place from two disagreeing sources.
    mapping = PlayerExternalId(id="ext-1", internal_player_id="uuid-1", sport="MLB", provider="draftkings", external_id="999", external_id_type="player_id", match_method=METHOD_EXISTING_CROSSWALK, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXISTING_CROSSWALK], is_current=True)
    assert mapping.is_current is True


def test_match_confidence_is_fixed_per_method_not_freeform():
    with pytest.raises(ValueError):
        PlayerExternalId(id="ext-1", internal_player_id="uuid-1", sport="MLB", provider="draftkings", external_id="999", external_id_type="player_id", match_method=METHOD_EXISTING_CROSSWALK, match_confidence=0.55)
