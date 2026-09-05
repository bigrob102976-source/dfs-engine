"""NFL M14 -- game lock-state model: PRELOCK vs LOCKED, computed purely
from DraftKings' own real game_start_time (an ISO-8601 UTC timestamp,
confirmed real and already timezone-aware -- see
nfl/models.py::NflPlayer.game_start_time and draftkings_unofficial/
normalizer.py's verbatim passthrough of DK's own `startTime` field).

Always timezone-aware, always compared in UTC internally -- never a
naive datetime comparison (NFL M14 Phase 4's explicit requirement).
Eastern display uses zoneinfo (America/New_York), which is DST-safe by
construction (it resolves EST/EDT from the real calendar date, never a
fixed UTC offset) and never depends on the host machine's own local
timezone setting (every conversion here names its target zone
explicitly -- .astimezone(timezone.utc) or .astimezone(EASTERN) --
never a bare .astimezone() call, which would silently fall back to the
system's local zone).

FINAL (a completed-game state) is deliberately NOT modeled: there is no
real live score/game-completion feed anywhere in this project
(confirmed by NFL M14 Phase 2's audit) -- inventing a "game over"
detection from nothing would violate this project's "never fabricate a
status" rule. LOCKED covers both "in progress" and "completed" for
late-swap purposes -- once a game's real start time has passed, that
player's roster spot is immutable regardless of whether the game is
still being played or has ended, which is the only distinction late
swap actually needs (see nfl/late_swap.py)."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

PRELOCK = "PRELOCK"
LOCKED = "LOCKED"

EASTERN = ZoneInfo("America/New_York")


class GameStartTimeMissingError(ValueError):
    """Raised when a lock decision is required but no real, valid
    game_start_time exists for the player/game -- never silently
    treated as either locked or unlocked."""


def parse_game_start_utc(game_start_time: Optional[str]) -> datetime:
    """Parses DK's real ISO-8601 game_start_time (e.g.
    "2026-09-13T17:00:00.0000000Z") into a timezone-aware UTC datetime.
    Raises GameStartTimeMissingError for anything else -- never guesses
    a start time."""
    if not game_start_time:
        raise GameStartTimeMissingError("game_start_time is missing -- cannot compute a real lock state.")
    try:
        dt = datetime.fromisoformat(game_start_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GameStartTimeMissingError(f"game_start_time {game_start_time!r} is not a valid ISO-8601 timestamp.") from exc
    if dt.tzinfo is None:
        raise GameStartTimeMissingError(f"game_start_time {game_start_time!r} is not timezone-aware.")
    return dt.astimezone(timezone.utc)


def compute_lock_state(game_start_time: Optional[str], now_utc: datetime) -> str:
    """`now_utc` MUST be timezone-aware (never naive) -- production
    callers pass datetime.now(timezone.utc); tests pass a fixed,
    explicit instant. NFL Classic has staggered game starts, so this is
    always evaluated PER GAME, never against a single slate-wide lock
    time."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware -- naive datetime comparisons are never allowed here.")
    start_utc = parse_game_start_utc(game_start_time)
    return LOCKED if now_utc >= start_utc else PRELOCK


def is_locked(game_start_time: Optional[str], now_utc: datetime) -> bool:
    return compute_lock_state(game_start_time, now_utc) == LOCKED


def format_eastern(game_start_time: Optional[str]) -> Optional[str]:
    """Human-readable Eastern-time display for NFL game-day UI, e.g.
    "Sat 09/13 01:00 PM EDT". DST-safe via zoneinfo -- %Z resolves to
    the real EST/EDT abbreviation for that calendar date, not a
    hardcoded offset. Portable strftime codes only (no GNU/BSD "-"
    no-pad flags, which are not supported by Windows' strftime)."""
    if not game_start_time:
        return None
    start_utc = parse_game_start_utc(game_start_time)
    eastern = start_utc.astimezone(EASTERN)
    return eastern.strftime("%a %m/%d %I:%M %p %Z")


@dataclass
class NflGameLockInfo:
    game_id: str
    start_time_utc: str  # ISO-8601, always UTC ("...+00:00")
    start_time_eastern: str  # display only
    home_team: Optional[str]
    away_team: Optional[str]
    lock_state: str  # PRELOCK | LOCKED
    locked: bool

    def to_dict(self) -> dict:
        return asdict(self)


def build_game_lock_info(
    game_id: str, game_start_time: str, now_utc: datetime,
    home_team: Optional[str] = None, away_team: Optional[str] = None,
) -> NflGameLockInfo:
    state = compute_lock_state(game_start_time, now_utc)
    start_utc = parse_game_start_utc(game_start_time)
    eastern_display = format_eastern(game_start_time)
    return NflGameLockInfo(
        game_id=game_id, start_time_utc=start_utc.isoformat(), start_time_eastern=eastern_display or "",
        home_team=home_team, away_team=away_team, lock_state=state, locked=(state == LOCKED),
    )
