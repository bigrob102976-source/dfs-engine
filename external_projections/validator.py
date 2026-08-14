"""Validates a provider's normalized output before it is ever persisted
as a baseline snapshot. Mirrors dfs/slate_validation.py in spirit --
returns a list of human-readable warning strings, never raises, never
silently drops or "fixes" bad data. An empty list means nothing was
found wrong; it is not a guarantee the data is meaningful."""

from typing import List

from external_projections.models import ExternalProjectionPlayer


def validate_external_players(players: List[ExternalProjectionPlayer]) -> List[str]:
    """Checks required-field presence/type and cross-player consistency.
    Every check here is about STRUCTURE (is this normalized output
    trustworthy enough to persist), never about the projection VALUES
    themselves (a provider is free to think a player projects for 0)."""
    warnings: List[str] = []

    if not players:
        warnings.append("Provider returned zero players.")
        return warnings

    seen_ids = {}
    for p in players:
        if not p.external_player_id:
            warnings.append(f"Player {p.name!r} is missing external_player_id.")
        elif p.external_player_id in seen_ids:
            warnings.append(f"Duplicate external_player_id {p.external_player_id!r} ({p.name!r} and {seen_ids[p.external_player_id]!r}).")
        else:
            seen_ids[p.external_player_id] = p.name

        if not p.name:
            warnings.append(f"Player {p.external_player_id!r} is missing a name.")
        if not p.team:
            warnings.append(f"Player {p.name!r} is missing team.")
        if not isinstance(p.projection, (int, float)):
            warnings.append(f"Player {p.name!r} has a non-numeric projection: {p.projection!r}.")
        elif p.projection < 0:
            warnings.append(f"Player {p.name!r} has a negative projection: {p.projection}.")

        if p.ceiling is not None and p.floor is not None and p.ceiling < p.floor:
            warnings.append(f"Player {p.name!r} has ceiling ({p.ceiling}) below floor ({p.floor}).")
        if p.ownership_projection is not None and not (0 <= p.ownership_projection <= 100):
            warnings.append(f"Player {p.name!r} has an out-of-range ownership_projection: {p.ownership_projection}.")

        if not p.provider_name:
            warnings.append(f"Player {p.name!r} is missing provider_name.")
        if not p.updated_at:
            warnings.append(f"Player {p.name!r} is missing updated_at.")
        if not p.slate_id:
            warnings.append(f"Player {p.name!r} is missing slate_id.")

    return warnings
