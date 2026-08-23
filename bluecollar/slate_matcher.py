"""Matches a real DraftKings provider slate (Featured/Turbo/Afternoon/...,
from DRAFTKINGS_UNOFFICIAL_LIVE via dfs/providers/) to the corresponding
BlueCollar slate (external_projections/bluecollar_provider.py) for the
same date.

BlueCollar's schema has no explicit game-count/start-time fields of its
own -- both are embedded in the human-readable slate NAME string,
confirmed via live observation (2026-08-23):

    "1:35PM ET Main 8 Games"
    "2:10PM ET (Turbo) 4 Games"
    "3:10PM ET (Turbo) 2 Games"
    "4:10PM ET (Afternoon) 4 Games"

_parse_bluecollar_slate_name() below extracts (start_hour, start_minute,
type_word, game_count) from that string via a regex built from these
exact observed examples -- if BlueCollar ever changes their naming
convention, a slate whose name doesn't match the pattern is excluded
from matching entirely (never guessed at) rather than crashing.

Matching signals, in order of how hard a constraint they are:

  1. game_count -- HARD filter. A DK slate with N games can only match
     a BlueCollar slate whose name says N Games. This is the single
     most reliable signal (untouched by naming differences like DK's
     "Featured" vs BlueCollar's "Main").
  2. player_count closeness -- scored, not a hard filter (small day-to-
     day discrepancies are possible even for the same real slate).
  3. start_time closeness -- scored (BlueCollar's ET start time vs DK's
     own start_time, converted to ET).
  4. slate-name keyword overlap -- scored (helps disambiguate two
     same-game-count slates, e.g. two Turbo slates, when player_count/
     start_time are also close).

If, after game_count filtering, more than one BlueCollar slate remains
and no single candidate's combined score clearly separates it from the
next-best by BLUECOLLAR_MATCH_MARGIN, the match is ambiguous --
BLUECOLLAR_SLATE_MATCH_AMBIGUOUS is returned, never a guess.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bluecollar.models import BlueCollarSlateMatch
from external_projections.models import ExternalSlateInfo

# ET is UTC-4 (EDT, in-season) for the entire MLB regular season this
# project's dates fall within -- a fixed offset, not a full tz database
# lookup, consistent with this project's existing "no new heavyweight
# dependency for a small conversion" discipline.
_ET_UTC_OFFSET_HOURS = -4

STATUS_MATCHED = "matched"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NO_BLUECOLLAR_SLATES = "no_bluecollar_slates"
STATUS_NO_CANDIDATE = "no_candidate"

# Scoring weights (0-1 each, blended) -- centralized here, not scattered.
_PLAYER_COUNT_WEIGHT = 0.35
_START_TIME_WEIGHT = 0.40
_NAME_OVERLAP_WEIGHT = 0.25

# The leading candidate's blended score must exceed the runner-up's by
# at least this much to be accepted as unambiguous.
BLUECOLLAR_MATCH_MARGIN = 0.15

_NAME_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*ET\s*\(?([A-Za-z]+)\)?\s*(\d+)\s*Games?\s*$",
    re.IGNORECASE,
)


class ParsedBlueCollarSlateName:
    __slots__ = ("start_hour_et", "start_minute_et", "type_word", "game_count")

    def __init__(self, start_hour_et: int, start_minute_et: int, type_word: str, game_count: int):
        self.start_hour_et = start_hour_et
        self.start_minute_et = start_minute_et
        self.type_word = type_word
        self.game_count = game_count


def parse_bluecollar_slate_name(name: Optional[str]) -> Optional[ParsedBlueCollarSlateName]:
    """Returns None (never raises) for a name that doesn't match the
    observed convention -- that slate is simply excluded from matching."""
    if not name:
        return None
    m = _NAME_RE.match(name)
    if not m:
        return None
    hour12, minute, ampm, type_word, game_count = m.groups()
    hour12 = int(hour12)
    if not (1 <= hour12 <= 12):
        return None
    hour24 = hour12 % 12
    if ampm.upper() == "PM":
        hour24 += 12
    return ParsedBlueCollarSlateName(
        start_hour_et=hour24, start_minute_et=int(minute), type_word=type_word.lower(), game_count=int(game_count),
    )


def _et_minutes_of_day_from_utc_iso(start_time_utc: Optional[str]) -> Optional[int]:
    if not start_time_utc:
        return None
    try:
        dt = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    et = dt.astimezone(timezone(timedelta(hours=_ET_UTC_OFFSET_HOURS)))
    return et.hour * 60 + et.minute


def _name_keyword_overlap(dk_name: Optional[str], bc_type_word: str) -> float:
    if not dk_name:
        return 0.0
    dk_words = {w.lower() for w in re.findall(r"[A-Za-z]+", dk_name)}
    return 1.0 if bc_type_word in dk_words else 0.0


def match_dk_slate_to_bluecollar(
    dk_slate: dict, bluecollar_slates: List[ExternalSlateInfo],
) -> BlueCollarSlateMatch:
    """`dk_slate` is one entry from a real provider_slate_<ts>.json's
    `slates` list (ProviderSlateInfo.to_dict() shape) -- must carry
    `slate_id`, `game_count`, `player_count`, and optionally
    `slate_name`/`start_time`."""
    dk_slate_id = dk_slate.get("slate_id") or dk_slate.get("slateId") or ""

    if not bluecollar_slates:
        return BlueCollarSlateMatch(status=STATUS_NO_BLUECOLLAR_SLATES, dk_slate_id=dk_slate_id, reason="BlueCollar returned no slates for this date.")

    dk_game_count = dk_slate.get("game_count")
    parsed_by_id = {s.slate_id: parse_bluecollar_slate_name(s.slate_name) for s in bluecollar_slates}

    if dk_game_count is not None:
        candidates = [s for s in bluecollar_slates if parsed_by_id[s.slate_id] is not None and parsed_by_id[s.slate_id].game_count == dk_game_count]
    else:
        # No DK game_count available at all -- can't apply the hard
        # filter safely, so every parseable BlueCollar slate stays in
        # play for scoring (still never a blind first-slate guess).
        candidates = [s for s in bluecollar_slates if parsed_by_id[s.slate_id] is not None]

    if not candidates:
        return BlueCollarSlateMatch(
            status=STATUS_NO_CANDIDATE, dk_slate_id=dk_slate_id,
            reason=f"No BlueCollar slate has a parseable name matching {dk_game_count} game(s).",
        )

    if len(candidates) == 1:
        only = candidates[0]
        return BlueCollarSlateMatch(status=STATUS_MATCHED, dk_slate_id=dk_slate_id, bluecollar_slate_id=only.slate_id, bluecollar_slate_name=only.slate_name)

    dk_player_count = dk_slate.get("player_count")
    dk_et_minutes = _et_minutes_of_day_from_utc_iso(dk_slate.get("start_time"))
    dk_name = dk_slate.get("slate_name")

    scored = []
    for s in candidates:
        parsed = parsed_by_id[s.slate_id]
        player_score = 0.5
        if dk_player_count and s.player_count:
            player_score = max(0.0, 1.0 - abs(dk_player_count - s.player_count) / max(dk_player_count, s.player_count))
        time_score = 0.5
        if dk_et_minutes is not None:
            bc_minutes = parsed.start_hour_et * 60 + parsed.start_minute_et
            diff = min(abs(dk_et_minutes - bc_minutes), 1440 - abs(dk_et_minutes - bc_minutes))
            time_score = max(0.0, 1.0 - diff / 60.0)  # within an hour matters; beyond that, treat as unrelated
        name_score = _name_keyword_overlap(dk_name, parsed.type_word)
        blended = _PLAYER_COUNT_WEIGHT * player_score + _START_TIME_WEIGHT * time_score + _NAME_OVERLAP_WEIGHT * name_score
        scored.append((blended, s))

    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_slate = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else -1.0

    if best_score - runner_up_score < BLUECOLLAR_MATCH_MARGIN:
        return BlueCollarSlateMatch(
            status=STATUS_AMBIGUOUS, dk_slate_id=dk_slate_id,
            reason=f"Multiple BlueCollar slates with {dk_game_count} game(s) score too closely to disambiguate safely.",
            candidate_slate_ids=[s.slate_id for _, s in scored],
        )

    return BlueCollarSlateMatch(status=STATUS_MATCHED, dk_slate_id=dk_slate_id, bluecollar_slate_id=best_slate.slate_id, bluecollar_slate_name=best_slate.slate_name)
