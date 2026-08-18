"""Milestone 27.1 -- deterministic provider-event resolution.

CONFIRMED REAL BUG this module fixes: on 2026-08-18, SportsGameOdds
returned THREE separate LAD @ COL events (a real 3-game series) --
yesterday's (already in the 6th inning), today's (upcoming, 8 books
posted), and tomorrow's (upcoming, no market yet). The previous matcher
(`vegas.py::_find_matching_event`, now superseded by this module)
matched ONLY on team names and returned the FIRST list match, which
happened to be YESTERDAY's already-in-play event -- so Big Money DFS
discarded a fully valid, currently-available pregame market for TODAY's
game and reported it as already in-play. Team names alone can never
disambiguate a same-teams-multiple-dates series; this module additionally
requires the provider event's own scheduled start to fall within a
configured tolerance of the authoritative MLB scheduled start.

Resolution rule (exact order):
    1. Filter provider events to ones matching (home_team, away_team).
    2. If no authoritative MLB scheduled start is available, fall back to
       the old team-only behavior ONLY when it's unambiguous (exactly one
       team match) -- multiple team matches with no time to disambiguate
       is always AMBIGUOUS, never a guess.
    3. Otherwise, keep only team-matches whose OWN scheduled start is
       within EVENT_MATCH_TOLERANCE_SECONDS of the MLB scheduled start.
    4. Exactly one survivor -> MATCHED. Zero -> NOT_MATCHED (a real gap,
       not this game). More than one -> AMBIGUOUS (e.g. a same-day
       doubleheader where two games are close enough in time that this
       project cannot confidently tell them apart without an authoritative
       per-game start-time source finer than what's compared here) --
       Vegas contribution is zero rather than guessing.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from research.game_environment.providers.models import NormalizedGameOdds

MATCHED = "MATCHED"
NOT_MATCHED = "NOT_MATCHED"
AMBIGUOUS = "AMBIGUOUS"

# 4 hours: generous enough to absorb a legitimate MLB rain delay/reschedule
# (this project's own real data showed a 4h40m delay on one game -- see
# this module's docstring) while still being far short of the ~20-24
# hours that separates one day's game from the next day's game in the
# same series. Named/configurable here, not scattered as a magic number.
EVENT_MATCH_TOLERANCE_SECONDS = 4 * 3600


def _parse_iso_utc(ts: Optional[str]) -> Optional[datetime]:
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


@dataclass
class EventResolution:
    event: Optional[NormalizedGameOdds]
    status: str  # MATCHED | NOT_MATCHED | AMBIGUOUS
    candidates_considered: int  # how many team-name matches existed, before time filtering

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "candidates_considered": self.candidates_considered,
            "matched_event_id": self.event.event_id if self.event else None,
        }


def resolve_provider_event(
    events: List[NormalizedGameOdds],
    home_team_abbr: str,
    away_team_abbr: str,
    mlb_scheduled_start_utc: Optional[str] = None,
    tolerance_seconds: int = EVENT_MATCH_TOLERANCE_SECONDS,
) -> EventResolution:
    team_matches = [e for e in events if e.home_team == home_team_abbr and e.away_team == away_team_abbr]
    if not team_matches:
        return EventResolution(None, NOT_MATCHED, 0)

    if len(team_matches) == 1 and mlb_scheduled_start_utc is None:
        # Only ever a silent single-candidate pass-through when there is
        # truly nothing to disambiguate -- multiple same-team events
        # NEVER fall through this branch, even without an MLB timestamp.
        return EventResolution(team_matches[0], MATCHED, 1)

    mlb_dt = _parse_iso_utc(mlb_scheduled_start_utc)
    if mlb_dt is None:
        # No authoritative time available and more than one team-match
        # exists (or exactly one, but we can't confirm it's the right
        # date at all) -- never guess which date's event this is.
        if len(team_matches) == 1:
            return EventResolution(team_matches[0], MATCHED, 1)
        return EventResolution(None, AMBIGUOUS, len(team_matches))

    within_tolerance = []
    for e in team_matches:
        event_dt = _parse_iso_utc(e.game_time_utc)
        if event_dt is not None and abs((event_dt - mlb_dt).total_seconds()) <= tolerance_seconds:
            within_tolerance.append(e)

    if len(within_tolerance) == 1:
        return EventResolution(within_tolerance[0], MATCHED, len(team_matches))
    if len(within_tolerance) == 0:
        return EventResolution(None, NOT_MATCHED, len(team_matches))
    return EventResolution(None, AMBIGUOUS, len(team_matches))
