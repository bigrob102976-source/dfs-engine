"""Milestone 32.2B -- pregame lock/freeze decision for one pitcher's
shadow ML projection. Reuses the SAME point-in-time game-status
machinery the Vegas pregame-lock system already established
(research.game_environment.game_status) rather than inventing a second
notion of "pregame." See research/game_environment/vegas.py for the
precedent this mirrors.
"""

from datetime import datetime, timezone
from typing import Optional

from research.game_environment.game_status import PREGAME, resolve_game_status

GENERATE = "GENERATE"
FREEZE_EXISTING = "FREEZE_EXISTING"
NO_VALID_PREGAME = "NO_VALID_PREGAME"


def _parse_iso_utc(ts: Optional[str]) -> Optional[datetime]:
    """Same permissive parsing as game_status.py's own private helper
    (accepts a trailing 'Z', treats a naive timestamp as already-UTC).
    Duplicated (not imported -- that helper is private) rather than
    reimplemented differently, so both modules agree on every edge case."""
    if not ts:
        return None
    try:
        cleaned = ts.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def determine_action(
    *,
    mlb_detailed_state: Optional[str],
    game_scheduled_start_utc: Optional[str],
    existing_projection_status: Optional[str],
    now_utc: Optional[datetime] = None,
) -> str:
    """
    GENERATE           -- game has not started; safe to compute a fresh
                           LIVE_PREGAME projection.
    FREEZE_EXISTING     -- game has started (or its status can no longer
                           be confirmed pregame) but a prior LIVE_PREGAME
                           snapshot exists for this pitcher; carry it
                           forward unchanged, never regenerate.
    NO_VALID_PREGAME     -- game has started and no prior pregame
                           projection was ever captured; report
                           "NO VALID PREGAME ML PROJECTION," never
                           generate one retroactively.
    """
    now_utc = now_utc or datetime.now(timezone.utc)

    # Hard wall-clock guard, checked FIRST: a game can never still be
    # legitimately "pregame" once its own authoritative scheduled start
    # has passed, no matter what a possibly-stale games.json status
    # field claims (research_output/<date>/games.json is only as fresh
    # as the last research-package build -- see resolve_game_status's
    # own docstring for the confirmed real-world case of this). This is
    # the mirror image of game_has_not_started_yet's guard (which
    # protects against a game being wrongly promoted forward too
    # early); this one protects the opposite staleness direction.
    scheduled = _parse_iso_utc(game_scheduled_start_utc)
    if scheduled is not None and now_utc >= scheduled:
        if existing_projection_status == "LIVE_PREGAME":
            return FREEZE_EXISTING
        return NO_VALID_PREGAME

    status = resolve_game_status(mlb_detailed_state, mlb_scheduled_start_utc=game_scheduled_start_utc, now_utc=now_utc)

    if status == PREGAME:
        return GENERATE

    if existing_projection_status == "LIVE_PREGAME":
        return FREEZE_EXISTING

    return NO_VALID_PREGAME
