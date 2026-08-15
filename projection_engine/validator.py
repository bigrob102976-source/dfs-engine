"""Validation for the AI Projection Engine's output -- a final,
defensive sweep after scoring.py builds every record. Rejects (never
silently drops) a player whose AI Projection is missing, non-finite, or
negative; every rejection is reported as a warning string, per
CLAUDE.md's "fail loudly when critical DFS data is missing" rule.
"""

from typing import List, Tuple

from projection_engine.models import AIPlayerProjection
from projection_engine.weights import is_finite_number


def validate_ai_player(player: AIPlayerProjection) -> List[str]:
    """Every reason this single player's AI Projection is invalid --
    empty list means valid."""
    errors: List[str] = []
    if not player.player_id:
        errors.append("missing player_id")
    if not player.name:
        errors.append("missing name")

    if player.ai_projection is None:
        errors.append("missing AI Projection")
    elif not is_finite_number(player.ai_projection):
        errors.append(f"AI Projection is not a finite number ({player.ai_projection!r})")
    elif player.ai_projection < 0:
        errors.append(f"AI Projection is negative ({player.ai_projection})")

    for field_name in ("ai_ceiling", "ai_floor"):
        value = getattr(player, field_name)
        if value is None:
            continue
        if not is_finite_number(value):
            errors.append(f"{field_name} is not a finite number ({value!r})")
        elif value < 0:
            errors.append(f"{field_name} is negative ({value})")

    return errors


def validate_ai_projection_slate(players: List[AIPlayerProjection]) -> Tuple[List[AIPlayerProjection], List[str]]:
    """Splits `players` into (valid, warnings). Every rejected player is
    named in a warning string -- never dropped silently."""
    valid: List[AIPlayerProjection] = []
    warnings: List[str] = []
    for player in players:
        errors = validate_ai_player(player)
        if errors:
            label = player.name or player.player_id or "<unknown player>"
            warnings.append(f"Rejected {label}: {'; '.join(errors)}")
        else:
            valid.append(player)
    return valid, warnings
