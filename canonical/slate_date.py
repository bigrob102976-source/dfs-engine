"""M1A -- the canonical slateDate contract.

Definition (per the M0 architecture audit and M1 task): slateDate is the
US/Eastern CALENDAR DATE of a slate's FIRST scheduled game start,
formatted YYYY-MM-DD.

This is deliberately NOT any of:
  - the server's "today" (would misclassify a slate looked up hours
    after its games started, or before the day's fetch has even run)
  - the browser's local date (viewer-timezone-dependent, not a property
    of the slate itself)
  - America/Chicago "today" (dashboard/lib/currentDate.ts's convention
    for "what day is it right now" -- a different question from "which
    calendar day does this slate belong to")
  - a bare UTC calendar date (a 7:05pm ET game start is already the
    next UTC calendar day for roughly 5 hours a night)
  - DraftKings' own StartDateEst slate-bucketing field, taken as-is (the
    M0 audit found this field describes when DK grouped the slate for
    its own lobby, not necessarily the true first-game-start instant --
    see compute_slate_date's docstring)

slateDate is computed ONCE, from the normalized game list's real
timezone-aware start instants, and is IMMUTABLE for that slate's
canonical identity thereafter -- see IMMUTABLE STORAGE SEMANTICS below.

M1 does NOT wire this function into any production read/write path
(dashboard/lib/currentDate.ts, dashboard/lib/slateDate.ts, the DK
worker, and poolCache.ts are all left untouched). It is foundation for
a later milestone that assigns slateDate to newly normalized
CanonicalSlate rows.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

DATE_FORMAT = "%Y-%m-%d"


class InvalidGameStartError(ValueError):
    """Raised when no usable timezone-aware game-start instant is given.
    Never silently defaults to "today" or any other fabricated date --
    per the M1 non-negotiable rule against fabricating slate data."""


def _parse_instant(value: str) -> datetime:
    """Parses a real ISO-8601 instant string into an aware UTC datetime.
    Accepts a trailing 'Z' (not natively understood by
    datetime.fromisoformat on this project's Python baseline) by
    normalizing it to '+00:00' first. Raises InvalidGameStartError (never
    guesses) for anything that isn't a genuine, unambiguous instant --
    in particular, a bare offset-less string (e.g. DraftKings' raw
    StartDateEst field) is REJECTED here on purpose: that field is
    already-local Eastern wall-clock time with no UTC anchor, and this
    function's job is to derive slateDate FROM a real instant, not to
    reinterpret an ambiguous provider field. Callers holding only a
    bare Eastern wall-clock string should attach the UTC offset
    DraftKings itself reports for the same game (its `StartDate` field)
    before calling this function, never guess an offset here."""
    if not value:
        raise InvalidGameStartError("Game start instant is empty -- refusing to fabricate a slateDate.")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise InvalidGameStartError(f"Could not parse '{value}' as a real ISO-8601 instant: {exc}") from exc
    if parsed.tzinfo is None:
        raise InvalidGameStartError(
            f"'{value}' has no timezone/UTC-offset information -- refusing to guess one. "
            "slateDate must be derived from a real, timezone-aware instant."
        )
    return parsed.astimezone(timezone.utc)


def compute_slate_date(first_game_start_utc: str) -> str:
    """Returns the US/Eastern calendar date (YYYY-MM-DD) of the given
    game-start instant. `first_game_start_utc` must be a real,
    timezone-aware ISO-8601 instant string (UTC or any explicit offset)
    -- the EARLIEST scheduled game start across the whole slate, per the
    slateDate contract. This function does not itself select "the
    earliest game" from a list; callers pass the one instant that has
    already been identified as the slate's first game start (see
    compute_slate_date_from_game_starts for the list-taking convenience
    wrapper).

    Correctly handles the US Eastern DST boundary via zoneinfo's real
    IANA tzdata (America/New_York), not a fixed UTC-4/UTC-5 offset."""
    instant_utc = _parse_instant(first_game_start_utc)
    instant_eastern = instant_utc.astimezone(EASTERN)
    return instant_eastern.strftime(DATE_FORMAT)


def compute_slate_date_from_game_starts(game_start_instants: list) -> str:
    """Convenience wrapper: given every game's start instant on a slate
    (real ISO-8601 strings, any explicit offset), finds the earliest one
    and returns its US/Eastern calendar date. Raises InvalidGameStartError
    if the list is empty -- an empty game list must never silently
    produce a fabricated slateDate."""
    if not game_start_instants:
        raise InvalidGameStartError("No game start instants provided -- refusing to fabricate a slateDate.")
    parsed = [_parse_instant(s) for s in game_start_instants]
    earliest = min(parsed)
    return earliest.astimezone(EASTERN).strftime(DATE_FORMAT)


class SlateDateImmutabilityError(ValueError):
    """Raised by enforce_slate_date_immutable when a caller attempts to
    assign a different slateDate to a canonical slate identity that
    already has one recorded. A later game postponement/reschedule that
    shifts the true first-game-start instant must NOT move an existing
    DraftGroup's row between date partitions -- see this module's own
    docstring and the M1A task requirement. The reschedule is still
    real and should be reflected in firstGameStartUtc / a fresh
    validation pass; slateDate itself, once assigned, stays put."""


def enforce_slate_date_immutable(stored_slate_date: str, newly_computed_slate_date: str) -> str:
    """The single choke point every write path MUST call before
    persisting a (re)computed slateDate for a canonical slate that may
    already exist. `stored_slate_date` is None for a brand-new slate
    (first assignment always wins). For an existing slate, a mismatch
    raises rather than silently repartitioning -- callers that expect a
    reschedule are responsible for handling that error explicitly
    (e.g. flagging it for manual review), never for calling this
    function again with the new value and treating a raise as "retry."
    """
    if stored_slate_date is None:
        return newly_computed_slate_date
    if stored_slate_date != newly_computed_slate_date:
        raise SlateDateImmutabilityError(
            f"Refusing to move canonical slate from stored slateDate '{stored_slate_date}' to "
            f"newly computed '{newly_computed_slate_date}' -- slateDate is immutable once assigned."
        )
    return stored_slate_date
