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

Wall-clock time (game_datetime_utc vs "now") is never used to classify
status -- only to label displayed lock/start times.
"""

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


def resolve_game_status(mlb_detailed_state: Optional[str], sgo_status: Optional[dict] = None) -> str:
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
    In every other case MLB wins when recognized; SportsGameOdds is only
    a fallback when MLB status is UNKNOWN/unrecognized -- EXCEPT that an
    explicit Postponed/Cancelled MLB status is never overridden back into
    PREGAME by a merely-absent/not-started SportsGameOdds status (that
    would defeat the whole point of treating Postponed as UNKNOWN)."""
    mlb_result = classify_mlb_game_status(mlb_detailed_state)
    sgo_result = classify_sportsgameodds_status(sgo_status)

    if mlb_result == PREGAME and sgo_result in (IN_PLAY, FINAL):
        return sgo_result

    if mlb_result != UNKNOWN:
        return mlb_result

    lowered = (mlb_detailed_state or "").strip().lower()
    if lowered in _MLB_EXPLICIT_NON_PREGAME_UNKNOWN_STATES:
        return UNKNOWN

    return sgo_result
