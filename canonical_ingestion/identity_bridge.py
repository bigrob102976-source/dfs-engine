"""M2E -- MLB identity bridge.

Reads the EXISTING MLB identity crosswalk (player_identity/, an
already-built, R2-backed system keyed by mlb_player_id) and resolves
each DraftKings draftable to it using ONE exact, deterministic,
non-fuzzy join: normalized player name + current team. This is
intentionally the ONLY automatic tier -- the M0 audit confirmed
player_identity's CanonicalIdentity.aliases (which would carry a
dk_player_id) is reserved but NOT YET POPULATED for any real player, so
there is no existing DK<->MLBAM crosswalk to look up directly; a
name+team exact match against a curated, live-roster-sourced identity
set (see player_identity/models.py::CanonicalIdentity's own docstring:
current_team always comes from the most recent live roster fetch) is
the one confident, non-fuzzy signal actually available today.

This does NOT migrate or modify player_identity/ in any way -- it only
reads player_identity.persistence.load_crosswalk()'s already-published
latest snapshot. No destructive migration, no new mutation of that
system, per M2E's explicit "build a bridge, not a migration" instruction.

Deliberately does NOT mint or assign internal_player_id -- Postgres
(and therefore the actual Player/PlayerExternalId rows) is owned
exclusively by the Node/TS side of this codebase (see
canonical_ingestion/__init__.py's docstring). This module only produces
a DETERMINISTIC MATCH DECISION plus external-id hints; the Postgres
promotion step (dashboard/scripts/promote-canonical-slate.ts) is what
actually looks up-or-mints the internal Player row, using exactly the
decision computed here -- it never re-decides or fuzzy-matches on its
own.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from canonical.identity_models import (
    CONFIDENCE_BY_METHOD,
    METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING,
)
from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED, IDENTITY_STATUS_UNRESOLVED
from dfs.name_normalization import normalize_name
from player_identity.models import CanonicalIdentity
from player_identity.persistence import load_crosswalk


@dataclass
class ExternalIdHint:
    provider: str
    external_id: str
    external_id_type: str

    def to_dict(self) -> dict:
        return {"provider": self.provider, "externalId": self.external_id, "externalIdType": self.external_id_type}


@dataclass
class DkIdentityBridgeResult:
    identity_status: str
    match_method: Optional[str] = None
    match_confidence: Optional[float] = None
    external_id_hints: List[ExternalIdHint] = field(default_factory=list)
    candidate_mlb_player_ids: List[str] = field(default_factory=list)
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "identityStatus": self.identity_status,
            "matchMethod": self.match_method,
            "matchConfidence": self.match_confidence,
            "externalIdHints": [h.to_dict() for h in self.external_id_hints],
            "candidateMlbPlayerIds": list(self.candidate_mlb_player_ids),
            "reason": self.reason,
        }


NameTeamIndex = Dict[Tuple[str, str], List[CanonicalIdentity]]


def build_name_team_index(crosswalk: Dict[str, CanonicalIdentity]) -> NameTeamIndex:
    """Groups every ACTIVE canonical identity by (normalized_name,
    current_team). More than one identity sharing a key is a genuine,
    real ambiguity (e.g. a name collision) -- surfaced as REVIEW_REQUIRED
    by resolve_dk_player, never silently resolved to either one."""
    index: NameTeamIndex = defaultdict(list)
    for identity in crosswalk.values():
        if not identity.active:
            continue
        index[(identity.normalized_name, identity.current_team)].append(identity)
    return dict(index)


def load_name_team_index() -> NameTeamIndex:
    """Convenience wrapper: loads player_identity's latest published
    crosswalk snapshot and builds the lookup index in one call. Never
    raises for "no crosswalk exists yet" -- load_crosswalk() itself
    returns {} in that case (a legitimate, if identity-bridge-inactive,
    state), which produces an empty index -- every DK player then
    resolves UNRESOLVED, never an error."""
    return build_name_team_index(load_crosswalk())


def resolve_dk_player(provider_player, index: NameTeamIndex) -> DkIdentityBridgeResult:
    """Resolves one dfs/providers/models.py ProviderPlayer against the
    MLB identity crosswalk index. Never fuzzy -- an exact dict lookup on
    (normalize_name(provider_player.name), provider_player.team); no
    edit-distance/similarity scoring exists anywhere in this path."""
    external_id_hints = [ExternalIdHint(provider="draftkings", external_id=provider_player.external_player_id, external_id_type="player_id")]

    normalized = normalize_name(provider_player.name)
    candidates = index.get((normalized, provider_player.team), [])

    if len(candidates) == 1:
        identity = candidates[0]
        external_id_hints.append(ExternalIdHint(provider="mlbam", external_id=identity.mlb_player_id, external_id_type="mlbam_id"))
        return DkIdentityBridgeResult(
            identity_status=IDENTITY_STATUS_RESOLVED,
            match_method=METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING,
            match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING],
            external_id_hints=external_id_hints,
            candidate_mlb_player_ids=[identity.mlb_player_id],
        )

    if len(candidates) > 1:
        return DkIdentityBridgeResult(
            identity_status=IDENTITY_STATUS_REVIEW_REQUIRED,
            external_id_hints=external_id_hints,
            candidate_mlb_player_ids=[c.mlb_player_id for c in candidates],
            reason=(
                f"{len(candidates)} MLB identity crosswalk entries share the exact normalized name "
                f"'{normalized}' and team '{provider_player.team}' -- genuine ambiguity, needs human review."
            ),
        )

    return DkIdentityBridgeResult(
        identity_status=IDENTITY_STATUS_UNRESOLVED,
        external_id_hints=external_id_hints,
        reason=f"No exact (normalized name, team) match in the MLB identity crosswalk for '{normalized}' / '{provider_player.team}'.",
    )
