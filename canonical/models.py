"""M1B / M1C / M1D -- canonical, sport-neutral slate models.

CanonicalSlate       one slate, independent of sport/site/provider.
CanonicalSlatePlayer one player on one canonical slate.
CanonicalSlateArtifact the immutable NORMALIZED artifact envelope that
                     wraps one CanonicalSlate + its CanonicalSlatePlayer
                     rows, plus artifact-level metadata (schemaVersion,
                     rawHash, normalizedHash).

Modeling correction carried over from the M0 review: schemaVersion/
rawHash/normalizedHash live ONCE on the artifact envelope, never
repeated on every player row. ProviderPlayer (dfs/providers/models.py)
already carries provider_draftable_ids -- a genuinely per-player,
per-slate field -- forward into CanonicalSlatePlayer.providerDraftableIds.

DraftKings semantics preserved throughout: providerPlayerId is the
provider's stable, player-level identity (DK's `playerId`);
providerDraftableIds is a LIST of the provider's slate/roster-slot-
specific identifiers (DK's `draftableId`) -- never collapsed into, and
never used as, canonical player identity (see canonical/identity_models.py).

This module is foundation only -- see canonical/__init__.py. No
production read/write path constructs these types yet.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from canonical.schema_version import CURRENT_SLATE_SCHEMA_VERSION

# -- CanonicalSlate.validationState --
VALIDATION_STATE_PENDING = "PENDING"
VALIDATION_STATE_VALID = "VALID"
VALIDATION_STATE_REJECTED = "REJECTED"
ALL_VALIDATION_STATES = frozenset({VALIDATION_STATE_PENDING, VALIDATION_STATE_VALID, VALIDATION_STATE_REJECTED})

# -- CanonicalSlatePlayer.identityStatus --
IDENTITY_STATUS_RESOLVED = "RESOLVED"
IDENTITY_STATUS_UNRESOLVED = "UNRESOLVED"
IDENTITY_STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
ALL_IDENTITY_STATUSES = frozenset({IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_UNRESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED})


@dataclass
class CanonicalSlate:
    """One slate, independent of sport/site/provider. internalSlateId is
    Big Money's own immutable identity for this canonical slate -- NEVER
    the provider's own slate identifier (providerSlateId carries that,
    e.g. DraftKings' DraftGroup ID verbatim, unmodified, never re-derived)."""

    internal_slate_id: str
    sport: str
    site: str
    provider: str
    provider_slate_id: str
    slate_name: Optional[str]
    slate_date: str  # YYYY-MM-DD, US/Eastern first-game-start -- see canonical/slate_date.py
    first_game_start_utc: str  # real ISO-8601 instant this slateDate was derived from
    game_count: Optional[int]
    game_ids: List[str] = field(default_factory=list)
    salary_cap: Optional[int] = None
    roster_template: Optional[Dict[str, int]] = None
    source_provenance: str = "UNKNOWN"
    validation_state: str = VALIDATION_STATE_PENDING
    validation_findings: List[str] = field(default_factory=list)
    fetched_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.validation_state not in ALL_VALIDATION_STATES:
            raise ValueError(f"Invalid validationState '{self.validation_state}' -- must be one of {sorted(ALL_VALIDATION_STATES)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "internalSlateId": self.internal_slate_id,
            "sport": self.sport,
            "site": self.site,
            "provider": self.provider,
            "providerSlateId": self.provider_slate_id,
            "slateName": self.slate_name,
            "slateDate": self.slate_date,
            "firstGameStartUtc": self.first_game_start_utc,
            "gameCount": self.game_count,
            "gameIds": list(self.game_ids),
            "salaryCap": self.salary_cap,
            "rosterTemplate": dict(self.roster_template) if self.roster_template else None,
            "sourceProvenance": self.source_provenance,
            "validationState": self.validation_state,
            "validationFindings": list(self.validation_findings),
            "fetchedAt": self.fetched_at,
        }


@dataclass
class CanonicalSlatePlayer:
    """One provider player on one canonical slate. internalPlayerId is
    NULLABLE by design -- an UNRESOLVED player is still a fully valid,
    servable slate player (see canonical/identity_matching.py); identity
    resolution must never block a valid slate from being served."""

    internal_slate_id: str
    provider_player_id: str
    name: str
    team: str
    salary: int
    position_eligibility: List[str]
    internal_player_id: Optional[str] = None
    provider_draftable_ids: List[str] = field(default_factory=list)
    opponent: Optional[str] = None
    game_id: Optional[str] = None
    roster_slot_eligibility: List[str] = field(default_factory=list)
    identity_status: str = IDENTITY_STATUS_UNRESOLVED

    def __post_init__(self) -> None:
        if self.identity_status not in ALL_IDENTITY_STATUSES:
            raise ValueError(f"Invalid identityStatus '{self.identity_status}' -- must be one of {sorted(ALL_IDENTITY_STATUSES)}")
        if self.identity_status == IDENTITY_STATUS_RESOLVED and self.internal_player_id is None:
            raise ValueError("identityStatus RESOLVED requires a non-null internalPlayerId.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "internalSlateId": self.internal_slate_id,
            "internalPlayerId": self.internal_player_id,
            "providerPlayerId": self.provider_player_id,
            "providerDraftableIds": list(self.provider_draftable_ids),
            "name": self.name,
            "team": self.team,
            "opponent": self.opponent,
            "gameId": self.game_id,
            "salary": self.salary,
            "positionEligibility": list(self.position_eligibility),
            "rosterSlotEligibility": list(self.roster_slot_eligibility),
            "identityStatus": self.identity_status,
        }


def slate_player_from_provider_player(provider_player, internal_slate_id: str, game_id: Optional[str] = None) -> CanonicalSlatePlayer:
    """Builds a CanonicalSlatePlayer from a dfs/providers/models.py
    ProviderPlayer -- the seam between the existing provider-normalized
    shape and the new canonical model. Identity is deliberately left
    UNRESOLVED here; assigning internalPlayerId is
    canonical/identity_matching.py's job, run separately (never inline
    during provider normalization, so a provider hiccup can never block
    on identity resolution)."""
    return CanonicalSlatePlayer(
        internal_slate_id=internal_slate_id,
        provider_player_id=provider_player.external_player_id,
        name=provider_player.name,
        team=provider_player.team,
        salary=provider_player.salary,
        position_eligibility=list(provider_player.position_eligibility),
        provider_draftable_ids=[str(d) for d in getattr(provider_player, "provider_draftable_ids", [])],
        opponent=provider_player.opponent,
        game_id=game_id,
        identity_status=IDENTITY_STATUS_UNRESOLVED,
    )


@dataclass
class CanonicalSlateArtifact:
    """The immutable NORMALIZED artifact envelope. Artifact-level
    metadata (schemaVersion, rawHash, normalizedHash) is stored ONCE
    here -- never repeated per player row."""

    slate: CanonicalSlate
    players: List[CanonicalSlatePlayer]
    raw_hash: Optional[str] = None
    normalized_hash: Optional[str] = None
    schema_version: str = CURRENT_SLATE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "rawHash": self.raw_hash,
            "normalizedHash": self.normalized_hash,
            "slate": self.slate.to_dict(),
            "players": [p.to_dict() for p in self.players],
        }
