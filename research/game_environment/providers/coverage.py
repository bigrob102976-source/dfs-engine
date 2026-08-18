"""Milestone 27 -- honest root-cause classification for a DK slate game
that did NOT end up with usable pregame Vegas data, across the whole
multi-provider (SportsGameOdds primary, The Odds API secondary)
pipeline. "Missing" alone is never good enough for this project to
report -- the user needs to know WHY, and whether an already-configured
secondary provider was even tried.

Categories (exact set the milestone specifies):

    EVENT_NOT_MATCHED        This provider returned events for the
                              league/date, but none matched this
                              specific away@home matchup at all.
    EVENT_MATCHED_NO_TOTAL   The event matched, but no book returned a
                              full-game total (over/under) market.
    EVENT_MATCHED_NO_MONEYLINE
                              The event matched and had a total, but no
                              book returned a full-game moneyline.
    PLAN_RESTRICTED          The provider rejected the request due to
                              plan/quota limits (HTTP 429, or an
                              authentication failure that looks like a
                              plan restriction rather than a bad key --
                              conservatively, this project only ever
                              maps a genuine rate-limit response here,
                              never guesses "plan restricted" from a
                              plain auth failure).
    PREGAME_NOT_AVAILABLE    The event matched and has markets, but the
                              game is no longer PREGAME (or was never
                              observed pregame) -- see game_status.py;
                              pregame lock rules forbid using it.
    PROVIDER_ERROR            The provider was configured but the
                              request itself failed (network error,
                              malformed response, unexpected HTTP
                              status) -- distinct from "not configured"
                              and from "not matched."
    UNKNOWN                   None of the above cleanly applies (e.g.
                              the provider was never attempted because
                              an earlier one already produced a valid
                              result, or the provider isn't configured
                              at all).
"""

from dataclasses import asdict, dataclass
from typing import Optional

EVENT_NOT_MATCHED = "EVENT_NOT_MATCHED"
EVENT_MATCHED_NO_TOTAL = "EVENT_MATCHED_NO_TOTAL"
EVENT_MATCHED_NO_MONEYLINE = "EVENT_MATCHED_NO_MONEYLINE"
PLAN_RESTRICTED = "PLAN_RESTRICTED"
PREGAME_NOT_AVAILABLE = "PREGAME_NOT_AVAILABLE"
PROVIDER_ERROR = "PROVIDER_ERROR"
UNKNOWN = "UNKNOWN"
NOT_CONFIGURED = "NOT_CONFIGURED"  # not one of the 8 "missing" reasons -- means "never attempted"
VALID = "VALID"  # not a missing reason -- the provider produced usable data

# Milestone 27.1: the provider returned MULTIPLE same-team events (a
# real series can have the same matchup on consecutive days) and none
# could be confidently disambiguated by scheduled start time against the
# authoritative MLB start (see providers/event_resolver.py). Distinct
# from EVENT_NOT_MATCHED (zero candidates) -- this is "too many,
# unresolvable," never a guess at which one is right.
EVENT_MATCH_AMBIGUOUS = "EVENT_MATCH_AMBIGUOUS"

ALL_MISSING_REASONS = (
    EVENT_NOT_MATCHED,
    EVENT_MATCHED_NO_TOTAL,
    EVENT_MATCHED_NO_MONEYLINE,
    PLAN_RESTRICTED,
    PREGAME_NOT_AVAILABLE,
    PROVIDER_ERROR,
    UNKNOWN,
    EVENT_MATCH_AMBIGUOUS,
)


@dataclass
class ProviderAttempt:
    """One provider's outcome for one game -- always recorded, even when
    that provider was never actually queried (status=NOT_CONFIGURED) or
    was skipped because a higher-priority provider already won
    (status=UNKNOWN, detail explains why)."""

    provider: str
    status: str  # VALID | NOT_CONFIGURED | one of ALL_MISSING_REASONS
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def classify_missing_reason(
    *,
    is_configured: bool,
    event_matched: bool,
    has_total: bool,
    has_moneyline: bool,
    is_pregame: bool,
    provider_errored: bool,
    rate_limited: bool,
) -> str:
    """Pure decision table -- every input is something the caller
    already knows for certain (never guessed), so this never needs to
    fall back to UNKNOWN except in the genuinely ambiguous case where
    none of the specific signals fired."""
    if not is_configured:
        return NOT_CONFIGURED
    if rate_limited:
        return PLAN_RESTRICTED
    if provider_errored:
        return PROVIDER_ERROR
    if not event_matched:
        return EVENT_NOT_MATCHED
    if not is_pregame:
        return PREGAME_NOT_AVAILABLE
    if not has_total:
        return EVENT_MATCHED_NO_TOTAL
    if not has_moneyline:
        return EVENT_MATCHED_NO_MONEYLINE
    return UNKNOWN
