"""M2C -- canonical normalization.

Converts an already-fetched, already-DK-structurally-validated
dfs/providers/models.py ProviderSlateInfo + its ProviderPlayer list
into a canonical/models.py CanonicalSlateArtifact, using ONLY M1's
existing canonical models -- this module invents no new shapes, and
never fabricates a value the provider genuinely didn't supply.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonical.hashing import compute_normalized_hash
from canonical.models import (
    CanonicalSlate,
    CanonicalSlateArtifact,
    CanonicalSlatePlayer,
    VALIDATION_STATE_REJECTED,
    VALIDATION_STATE_VALID,
    slate_player_from_provider_player,
)
from canonical.schema_version import CURRENT_SLATE_SCHEMA_VERSION
from canonical.slate_date import InvalidGameStartError, compute_slate_date_from_game_starts
from canonical_ingestion.identity_bridge import NameTeamIndex, resolve_dk_player
from dfs.providers.source_provenance import TRUSTED_FOR_PRODUCTION


class NormalizationError(ValueError):
    """Raised when a real provider result cannot be honestly normalized
    (e.g. no game-start instants available at all to derive slateDate)
    -- never falls back to a fabricated value."""


def build_canonical_artifact(
    *, sport: str, site: str, provider: str, slate_info, provider_players: List, internal_slate_id: str,
    raw_hash: Optional[str], name_team_index: NameTeamIndex, fetched_at: Optional[str] = None,
) -> CanonicalSlateArtifact:
    """`slate_info`/`provider_players` are dfs/providers/models.py's
    ProviderSlateInfo/ProviderPlayer -- the exact shapes
    DraftKingsUnofficialProvider.get_slate() already returns, after its
    own structural validation. `internal_slate_id` is a freshly proposed
    UUID (see canonical_ingestion.slate_identity) -- the Postgres
    promotion step is the actual authority on whether this becomes the
    real canonical id or an existing one is reused (M2D); this function
    does not query Postgres and never needs to.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()

    game_start_instants = [p.start_time for p in provider_players if p.start_time]
    if not game_start_instants:
        raise NormalizationError(
            f"No game-start instants available for {provider}:{slate_info.slate_id} -- refusing to fabricate a slateDate."
        )
    try:
        slate_date = compute_slate_date_from_game_starts(game_start_instants)
    except InvalidGameStartError as exc:
        raise NormalizationError(str(exc)) from exc
    first_game_start_utc = min(game_start_instants)  # real ISO-8601 UTC strings sort chronologically

    validation_state = VALIDATION_STATE_VALID if slate_info.source_provenance in TRUSTED_FOR_PRODUCTION else VALIDATION_STATE_REJECTED
    validation_findings = list(slate_info.realism_findings)

    canonical_slate = CanonicalSlate(
        internal_slate_id=internal_slate_id, sport=sport, site=site, provider=provider,
        provider_slate_id=slate_info.slate_id, slate_name=slate_info.slate_name, slate_date=slate_date,
        first_game_start_utc=first_game_start_utc, game_count=slate_info.game_count,
        game_ids=list(slate_info.game_ids), source_provenance=slate_info.source_provenance,
        validation_state=validation_state, validation_findings=validation_findings, fetched_at=fetched_at,
    )

    slate_players: List[CanonicalSlatePlayer] = []
    identity_matches: Dict[str, Dict[str, Any]] = {}
    for provider_player in provider_players:
        match = resolve_dk_player(provider_player, name_team_index)
        slate_player = slate_player_from_provider_player(provider_player, internal_slate_id=internal_slate_id)
        slate_player.identity_status = match.identity_status
        slate_players.append(slate_player)
        identity_matches[provider_player.external_player_id] = match.to_dict()

    artifact = CanonicalSlateArtifact(
        slate=canonical_slate, players=slate_players, raw_hash=raw_hash, schema_version=CURRENT_SLATE_SCHEMA_VERSION,
        identity_matches=identity_matches,
    )
    artifact.normalized_hash = compute_normalized_hash(canonical_slate.to_dict(), [p.to_dict() for p in slate_players])
    return artifact
