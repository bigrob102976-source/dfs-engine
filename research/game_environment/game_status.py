"""Game status classification (Milestone 25 -- Pregame Vegas Lock).

Classifies a game into exactly one of PREGAME / IN_PLAY / FINAL / UNKNOWN,
which every Vegas snapshot in this project now carries at capture time
(see vegas.py) to answer "was this specific pull taken before first
pitch?" -- the single fact the whole pregame-lock/freeze system is built
on.

Authority order (per this milestone's explicit instruction: "Do not
classify solely from local wall-clock time if authoritative game status
exists"):

  1. MLB Stats API's own `status.detailedState` for this game, already
     collected into research_output/<date>/games.json's "status" field
     by research/normalizer.py -- this is the SAME authoritative source
     research/adapters/pitcher_input.py already treats as ground truth
     for "is this pitcher confirmed to start." Real observed values in
     this project's own research_output/ (2026-08-13..17): "Scheduled",
     "Pre-Game", "Warmup", "In Progress", "Delayed", "Suspended",
     "Postponed", "Final", "Game Over".
  2. SportsGameOdds' own per-event `status` object (confirmed live,
     Milestone 24: {"started": bool, "live": bool, "ended": bool,
     "completed": bool, "cancelled": bool, "delayed": bool, ...}) --
     used only as a FALLBACK when MLB status is missing/unrecognized,
     since MLB Stats API is this project's one authoritative schedule
     source everywhere else (see engine.py's own module docstring).

Wall-clock time (game_datetime_utc vs "now") is never used to PROMOTE a
game's status (e.g. never "it's past first pitch so assume IN_PLAY") --
only to label displayed lock/start times, AND (Milestone 27.1) as an
"impossible state" GUARD that can only ever hold a game back at PREGAME,
never push it forward. See game_has_not_started_yet()'s own docstring.
"""

from datetime import datetime, timezone
from typing import Optional

PREGAME = "PREGAME"
IN_PLAY = "IN_PLAY"
FINAL = "FINAL"
UNKNOWN = "UNKNOWN"

# MLB Stats API detailedState strings, lowercased for matching. Not
# exhaustive by design -- an unrecognized string safely falls through to
# UNKNOWN rather than being guessed into PREGAME/IN_PLAY/FINAL.
_MLB_PREGAME_STATES = {"scheduled", "pre-game", "pregame", "warmup"}
_MLB_IN_PLAY_STATES = {
    "in progress",
    "delayed",
    "delayed start",
    "manager challenge",
    "review",
    "replay",
    "suspended",  # explicit per this milestone: a suspended game HAS started; its eventual
    # resumption is never treated as fresh pregame data (see vegas.py's snapshot selector,
    # which only ever looks for snapshots captured while classify_mlb_game_status()
    # returned PREGAME -- a game classified IN_PLAY here can never produce one).
}
_MLB_FINAL_STATES = {"final", "game over", "completed early", "final: tied"}
# Deliberately NOT mapped to PREGAME: "postponed", "cancelled" -- a
# postponed game hasn't started, but treating it as PREGAME would let a
# fresh fetch during the postponement window silently become the "last
# valid pregame snapshot" for whatever NEW date the game eventually gets
# rescheduled to, even though the market context (probable pitchers,
# weather day, etc.) may have completely reset. UNKNOWN correctly blocks
# that: it can never win snapshot selection, but any pregame snapshot
# already captured before the postponement stays available as a fallback,
# and a fresh PREGAME-classified snapshot is picked up automatically once
# MLB flips the game back to "Scheduled" for its new date/time.
#
# Tracked separately from "merely unrecognized" so resolve_game_status()
# can refuse to let a stale/absent SportsGameOdds status promote one of
# these deliberate UNKNOWNs back into PREGAME (see resolve_game_status's
# own docstring).
_MLB_EXPLICIT_NON_PREGAME_UNKNOWN_STATES = {"postponed", "cancelled"}


def classify_mlb_game_status(detailed_state: Optional[str]) -> str:
    if not detailed_state:
        return UNKNOWN
    lowered = detailed_state.strip().lower()
    if lowered in _MLB_PREGAME_STATES:
        return PREGAME
    if lowered in _MLB_IN_PLAY_STATES:
        return IN_PLAY
    if lowered in _MLB_FINAL_STATES:
        return FINAL
    return UNKNOWN


def classify_sportsgameodds_status(status: Optional[dict]) -> str:
    """Fallback classification from SportsGameOdds' own event `status`
    object -- only consulted when MLB status is unavailable/unrecognized
    (see resolve_game_status)."""
    if not isinstance(status, dict):
        return UNKNOWN
    if status.get("cancelled"):
        return UNKNOWN  # a cancelled game is neither a usable pregame nor in-play state
    if status.get("completed") or status.get("ended"):
        return FINAL
    if status.get("started") or status.get("live"):
        return IN_PLAY
    if status.get("started") is False:
        return PREGAME
    return UNKNOWN


def _parse_iso_utc(ts: Optional[str]) -> Optional[datetime]:
    """Parses an ISO-8601 timestamp (with or without a trailing "Z", with
    or without fractional seconds) into a timezone-AWARE UTC datetime.
    Returns None (never raises, never guesses) for anything unparseable
    -- callers must then treat the guard below as inapplicable rather
    than crash on a malformed provider timestamp."""
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
        # A naive timestamp from this project's own sources is always
        # already UTC (see this module's own docstring: never compare a
        # naive local timestamp against a UTC one) -- never silently
        # reinterpreted in another zone.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def game_has_not_started_yet(mlb_scheduled_start_utc: Optional[str], now_utc: Optional[datetime] = None) -> bool:
    """Milestone 27.1 "impossible state" guard: True only when we have an
    authoritative MLB scheduled start timestamp AND the current moment is
    still strictly before it. No real provider can honestly report a
    game IN_PLAY/FINAL before its own authoritative first pitch --  if
    one does, that's a signal the wrong event was matched (or the
    provider itself is stale/wrong), never a signal to trust it. Returns
    False (never blocks) whenever `mlb_scheduled_start_utc` is missing or
    unparseable -- this guard only ever HOLDS a game back at PREGAME, it
    never promotes one forward, so an inapplicable guard is always safe
    to skip rather than guess."""
    scheduled = _parse_iso_utc(mlb_scheduled_start_utc)
    if scheduled is None:
        return False
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    return now < scheduled


def resolve_game_status(
    mlb_detailed_state: Optional[str],
    sgo_status: Optional[dict] = None,
    *,
    mlb_scheduled_start_utc: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> str:
    """The one function callers should use.

    MLB status is preferred (it's this project's one authoritative
    schedule source everywhere else, and it alone models Postponed/
    Suspended) -- EXCEPT for one confirmed real-world case (Milestone 25
    live validation, 2026-08-17: LAD @ COL): research_output/<date>/
    games.json's MLB status is only as fresh as the last research-package
    build, so it can still read "Pre-Game" hours after a game has
    actually started if the research package wasn't rebuilt. SportsGameOdds'
    own event status, by contrast, is fetched fresh on every single pull.
    So: if MLB says PREGAME but SportsGameOdds confidently says the game
    has left pregame (IN_PLAY or FINAL), SportsGameOdds wins -- a stale
    "Pre-Game" must never let genuinely live/in-play odds be classified
    (and therefore used) as if they were still a valid pregame snapshot.

    Milestone 27.1: that override is ONLY trustworthy when the provider
    event is genuinely the SAME game (see providers/event_resolver.py --
    this project confirmed live that SportsGameOdds can return several
    same-team events across consecutive days of a series, and naive
    team-only matching can pick the wrong one). As a second, independent
    line of defense at the status layer itself: if `mlb_scheduled_start_utc`
    is provided and `now_utc` (defaults to the real current time) is
    still BEFORE it, an IN_PLAY/FINAL claim from SportsGameOdds is an
    impossible state -- no real game can be in progress before its own
    authoritative first pitch -- so it's rejected and MLB's own PREGAME
    is kept instead. See game_has_not_started_yet()'s docstring.

    In every other case MLB wins when recognized; SportsGameOdds is only
    a fallback when MLB status is UNKNOWN/unrecognized -- EXCEPT that an
    explicit Postponed/Cancelled MLB status is never overridden back into
    PREGAME by a merely-absent/not-started SportsGameOdds status (that
    would defeat the whole point of treating Postponed as UNKNOWN)."""
    mlb_result = classify_mlb_game_status(mlb_detailed_state)
    sgo_result = classify_sportsgameodds_status(sgo_status)

    if mlb_result == PREGAME and sgo_result in (IN_PLAY, FINAL):
        if game_has_not_started_yet(mlb_scheduled_start_utc, now_utc):
            return PREGAME
        return sgo_result

    if mlb_result != UNKNOWN:
        return mlb_result

    lowered = (mlb_detailed_state or "").strip().lower()
    if lowered in _MLB_EXPLICIT_NON_PREGAME_UNKNOWN_STATES:
        return UNKNOWN

    return sgo_result
