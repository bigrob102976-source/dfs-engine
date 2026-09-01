"""M1E / M1F / M1H -- sport-neutral player identity foundation.

Generalizes the identity design principles the M0 audit found in
nfl-dfs-engine/historical_nfl/identity_models.py (read-only reference --
this package does NOT import from the separate NFL repository, and NFL
code is not modified by this milestone):

  - an immutable internal player ID, minted once, never changed by a
    later external-ID discovery or correction
  - an explicit review-queue state, distinct from a plain boolean
    "matched or not"
  - a conflict-detection error, never a silent overwrite, when two
    resolutions disagree about the same external identifier
  - categorical, FIXED confidence values keyed to match method -- never
    a fuzzy/edit-distance similarity score used to decide a match

Unlike the NFL pattern, internalPlayerId here is a plain, provider-
agnostic identifier (e.g. a UUID) rather than a provider-prefixed
string (`gsis:...`/`dk:...`) -- multi-sport, multi-provider identity
should not bake one provider's ID namespace into the canonical key.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# -- PlayerExternalId.review_status --
REVIEW_AUTO_APPROVED = "AUTO_APPROVED"
REVIEW_NEEDS_REVIEW = "NEEDS_REVIEW"
REVIEW_REVIEWED_APPROVED = "REVIEWED_APPROVED"
REVIEW_REVIEWED_REJECTED = "REVIEWED_REJECTED"
ALL_REVIEW_STATUSES = frozenset({REVIEW_AUTO_APPROVED, REVIEW_NEEDS_REVIEW, REVIEW_REVIEWED_APPROVED, REVIEW_REVIEWED_REJECTED})

# -- match methods (M1G's allowed deterministic resolution methods,
# preference order -- never a fuzzy tier) --
METHOD_EXISTING_CROSSWALK = "existing_crosswalk"
METHOD_EXACT_REVIEWED_PROVIDER_MAPPING = "exact_reviewed_provider_mapping"
METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING = "exact_deterministic_source_mapping"
METHOD_EXCEPTION_TABLE = "exception_table"
METHOD_MANUAL_REVIEW = "manual_review"

# Fixed, deterministic confidence per method -- reporting/filtering
# metadata only, NEVER used to decide whether a match is accepted (the
# tier hierarchy alone decides that). No method here is a similarity
# score; every one is either "this exact identifier already resolved
# before," "a human already approved this exact mapping," "a
# deterministic, non-fuzzy join against a trusted source," or "a human
# is resolving this right now."
CONFIDENCE_BY_METHOD: Dict[str, float] = {
    METHOD_EXISTING_CROSSWALK: 1.0,
    METHOD_EXACT_REVIEWED_PROVIDER_MAPPING: 1.0,
    METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING: 1.0,
    METHOD_EXCEPTION_TABLE: 1.0,
    METHOD_MANUAL_REVIEW: 1.0,
}

# -- identity_review_queue.status --
REVIEW_QUEUE_PENDING = "PENDING"
REVIEW_QUEUE_RESOLVED = "RESOLVED"
REVIEW_QUEUE_REJECTED = "REJECTED"
ALL_REVIEW_QUEUE_STATUSES = frozenset({REVIEW_QUEUE_PENDING, REVIEW_QUEUE_RESOLVED, REVIEW_QUEUE_REJECTED})


@dataclass
class Player:
    """The canonical, sport-neutral player identity. internal_player_id
    is Big Money's own, minted once, and NEVER used interchangeably
    with any external identifier (name, DK playerId, MLBAM ID, GSIS ID,
    SportsDataIO ID) -- those attach via PlayerExternalId rows."""

    internal_player_id: str
    sport: str
    canonical_name: str
    normalized_name: str
    current_team: Optional[str] = None
    position: Optional[str] = None
    active: bool = True
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerExternalId:
    """One external identifier mapped to a canonical Player.
    Historical mappings are supported by design -- see M1F's explicit
    instruction NOT to enforce a permanent UNIQUE(internal_player_id,
    provider). `is_current` marks the single active mapping for a given
    (provider, sport, internal_player_id); `valid_from`/`valid_to`
    record the mapping's effective window. A provider may have more
    than one historical external_id for the same internal player (an ID
    migration), and this model supports that -- what it must never
    allow is one (provider, external_id, sport) CURRENTLY resolving to
    more than one internal player at the same time (enforced at the
    Postgres layer via a partial unique index -- see the M1I migration
    -- and at this layer via identity_matching.py's conflict check)."""

    id: str
    internal_player_id: str
    sport: str
    provider: str
    external_id: str
    external_id_type: str
    match_method: str
    match_confidence: float
    review_status: str = REVIEW_AUTO_APPROVED
    is_current: bool = True
    valid_from: str = ""
    valid_to: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.review_status not in ALL_REVIEW_STATUSES:
            raise ValueError(f"Invalid review_status '{self.review_status}'")
        expected_confidence = CONFIDENCE_BY_METHOD.get(self.match_method)
        if expected_confidence is not None and self.match_confidence != expected_confidence:
            raise ValueError(
                f"match_confidence for method '{self.match_method}' must be the fixed value "
                f"{expected_confidence} (categorical tier, never a fuzzy score), got {self.match_confidence}."
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdentityReviewQueueEntry:
    """One row a human must resolve -- created only when a provider
    player has plausible but conflicting/ambiguous candidate matches,
    never for a plain "no candidates at all" case (see
    canonical/identity_matching.py). A slate is never blocked while a
    queue entry is pending."""

    id: str
    sport: str
    provider: str
    external_id: str
    provider_player_name: str
    reason: str
    provider_team: Optional[str] = None
    provider_position: Optional[str] = None
    candidate_internal_player_id: Optional[str] = None
    status: str = REVIEW_QUEUE_PENDING
    resolved_internal_player_id: Optional[str] = None
    resolved_by: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    resolved_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in ALL_REVIEW_QUEUE_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CrosswalkConflictError(Exception):
    """Raised when a newly resolved (provider, external_id, sport) ->
    internal_player_id mapping disagrees with an existing CURRENT
    mapping for the same external identifier. Never silently
    overwritten -- the caller must route this to human review instead
    of applying either value automatically."""
