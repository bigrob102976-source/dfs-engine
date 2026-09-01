"""M1G -- generalized, sport-neutral identity resolution rules.

Deterministic tiers only, in preference order; NO fuzzy/similarity-score
tier exists anywhere in this module -- see canonical/identity_models.py's
CONFIDENCE_BY_METHOD for why. This is intentionally more conservative
than the NFL M6B pattern audited in M0 (nfl-dfs-engine/historical_nfl/
identity_matching.py), which includes an automatic name+position
cross-team tier backed by a curated nflverse roster source: no
equivalent curated, versioned roster source is wired into this
sport-neutral package yet, and guessing one would risk exactly the
fuzzy-auto-merge this milestone forbids. A future milestone may add an
additional exact (not fuzzy) tier once such a source is designated.

Resolution never blocks a slate: an unresolved player is UNMATCHED
(servable, internal_player_id left null); only a genuine plausible
AMBIGUITY between candidates produces REVIEW_REQUIRED and a queue entry.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from canonical.identity_models import (
    CONFIDENCE_BY_METHOD,
    CrosswalkConflictError,
    METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING,
    METHOD_EXACT_REVIEWED_PROVIDER_MAPPING,
    METHOD_EXCEPTION_TABLE,
    METHOD_EXISTING_CROSSWALK,
    METHOD_MANUAL_REVIEW,
)

# -- ephemeral per-attempt outcome (distinct from CanonicalSlatePlayer's
# persisted identityStatus, though MATCHED/UNMATCHED/AMBIGUOUS map onto
# RESOLVED/UNRESOLVED/REVIEW_REQUIRED one-to-one -- see
# identity_status_for_match_status below) --
STATUS_MATCHED = "MATCHED"
STATUS_UNMATCHED = "UNMATCHED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass
class IdentityMatchCandidate:
    """One provider player awaiting identity resolution."""

    sport: str
    provider: str
    external_id: str
    external_id_type: str
    name: str
    team: Optional[str] = None
    position: Optional[str] = None


@dataclass
class IdentityMatchResult:
    """The outcome of one resolution attempt. Never persisted directly --
    a MATCHED result is what a caller turns into a PlayerExternalId row
    (canonical/identity_models.py); a REVIEW_REQUIRED result is what
    becomes an IdentityReviewQueueEntry."""

    status: str
    internal_player_id: Optional[str] = None
    match_method: Optional[str] = None
    match_confidence: Optional[float] = None
    reason: Optional[str] = None
    candidate_internal_player_ids: List[str] = field(default_factory=list)


def identity_status_for_match_status(match_status: str) -> str:
    """Maps an ephemeral IdentityMatchResult.status onto the persisted
    CanonicalSlatePlayer.identityStatus vocabulary (canonical/models.py)."""
    from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED, IDENTITY_STATUS_UNRESOLVED

    if match_status == STATUS_MATCHED:
        return IDENTITY_STATUS_RESOLVED
    if match_status in (STATUS_AMBIGUOUS, STATUS_REVIEW_REQUIRED):
        return IDENTITY_STATUS_REVIEW_REQUIRED
    return IDENTITY_STATUS_UNRESOLVED


def resolve_identity(
    candidate: IdentityMatchCandidate,
    *,
    existing_crosswalk: Optional[Dict[str, str]] = None,
    reviewed_provider_mappings: Optional[Dict[str, str]] = None,
    deterministic_source_mappings: Optional[Dict[str, str]] = None,
    exception_table: Optional[Dict[str, str]] = None,
    ambiguous_candidate_internal_player_ids: Optional[List[str]] = None,
) -> IdentityMatchResult:
    """Attempts to resolve `candidate` to an internal_player_id using
    only deterministic, non-fuzzy tiers, in this preference order:

      1. existing_crosswalk        -- an is_current PlayerExternalId row
                                       already maps this exact
                                       (provider, external_id) pair.
      2. exact_reviewed_provider_mapping -- a human has already reviewed
                                       and approved this exact mapping
                                       (REVIEWED_APPROVED), just not yet
                                       recorded as the live crosswalk.
      3. exact_deterministic_source_mapping -- an exact (never fuzzy)
                                       join against a separately
                                       maintained, trusted source
                                       (e.g. a curated roster crosswalk)
                                       the caller supplies.
      4. exception_table           -- an explicit, curated override for
                                       known edge cases.

    Each dict, if given, is keyed by candidate.external_id ->
    internal_player_id. If none resolve it:

      - `ambiguous_candidate_internal_player_ids` empty or not given:
        UNMATCHED -- a genuinely new player, servable with a null
        internal_player_id, no review queue entry created.
      - `ambiguous_candidate_internal_player_ids` has one or more
        entries: REVIEW_REQUIRED -- plausible but unconfirmed
        candidates exist; a human must decide. The slate is still
        servable; only this player's identity is left unresolved
        pending review.

    Raises CrosswalkConflictError if more than one tier resolves this
    exact external_id to DIFFERENT internal_player_ids -- never silently
    picks one; a disagreement between two supposedly-authoritative
    sources must be surfaced, not guessed past."""
    tiers = (
        (METHOD_EXISTING_CROSSWALK, existing_crosswalk or {}),
        (METHOD_EXACT_REVIEWED_PROVIDER_MAPPING, reviewed_provider_mappings or {}),
        (METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING, deterministic_source_mappings or {}),
        (METHOD_EXCEPTION_TABLE, exception_table or {}),
    )

    resolved: List[tuple] = []
    for method, mapping in tiers:
        internal_id = mapping.get(candidate.external_id)
        if internal_id is not None:
            resolved.append((method, internal_id))

    if resolved:
        distinct_ids = {internal_id for _, internal_id in resolved}
        if len(distinct_ids) > 1:
            raise CrosswalkConflictError(
                f"Conflicting identity resolution for {candidate.provider}:{candidate.external_id} "
                f"(sport={candidate.sport}) -- tiers disagree: {resolved}. Refusing to auto-pick one."
            )
        method, internal_id = resolved[0]
        return IdentityMatchResult(
            status=STATUS_MATCHED,
            internal_player_id=internal_id,
            match_method=method,
            match_confidence=CONFIDENCE_BY_METHOD[method],
        )

    candidates = list(ambiguous_candidate_internal_player_ids or [])
    if candidates:
        return IdentityMatchResult(
            status=STATUS_REVIEW_REQUIRED,
            internal_player_id=None,
            match_method=None,
            match_confidence=None,
            reason=(
                f"No confirmed mapping for {candidate.provider}:{candidate.external_id}, but "
                f"{len(candidates)} plausible existing player(s) found -- needs human review, "
                "never auto-merged."
            ),
            candidate_internal_player_ids=candidates,
        )

    return IdentityMatchResult(
        status=STATUS_UNMATCHED,
        internal_player_id=None,
        match_method=None,
        match_confidence=None,
        reason=f"No existing mapping or plausible candidate for {candidate.provider}:{candidate.external_id} -- new player, servable unresolved.",
    )
