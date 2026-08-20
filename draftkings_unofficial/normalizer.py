"""Raw DraftKings JSON -> normalized draftkings_unofficial/models.py
objects. Every function here is pure (no network calls -- see
client.py for that) and defensive: a malformed individual record is
skipped and reported, never allowed to crash normalization of the
rest of the payload (see this milestone's "never silently drop
malformed records... log/report them" requirement) -- each normalize_*
function returns a `(records, skipped)` pair, `skipped` being a list of
{"raw": ..., "reason": ...} entries.

Two DraftKings quirks handled explicitly, not guessed at:

1. Contest start times arrive as ASP.NET's `/Date(1788306000000)/`
   format (milliseconds since epoch, embedded in a string) -- parsed to
   ISO 8601 by `_parse_dotnet_date`. The original raw string is always
   preserved on DkContest.start_time_raw regardless of parse success.

2. A roster slot's scoring multiplier (e.g. Showdown Captain's 1.5x) is
   only exposed as free text (`positionTipSubtext: "1.5x"`), never a
   clean numeric field -- parsed defensively by `_parse_multiplier`,
   None when absent/unparseable, never assumed to be 1.0.

NOT done here: DraftKings' draftStatAttributes on a draftable (e.g.
`{"id": 408, "value": "22.9"}`) has no self-describing label anywhere
in the payloads this milestone observed -- there is no evidence `id`
408 (or any other id) reliably means "FPPG" across sports/contexts, so
DkDraftable.fppg is deliberately left None rather than guessed; the
full raw attributes list is preserved on `.raw` either way. Per this
milestone's "do not invent fields."
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from draftkings_unofficial import schema_guard
from draftkings_unofficial.models import (
    DkContest,
    DkDraftable,
    DkGameType,
    DkRosterRules,
    DkRosterSlot,
    DkSlate,
    DkSlateGame,
    DkSport,
    DkTeam,
)

_DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")
_MULTIPLIER_RE = re.compile(r"([\d.]+)\s*x", re.IGNORECASE)

SkipEntry = Dict[str, Any]


def _parse_dotnet_date(raw: Optional[str]) -> Optional[str]:
    """"/Date(1788306000000)/" -> "2026-08-20T22:35:00+00:00". Returns
    None (never raises, never guesses) when `raw` doesn't match the
    expected shape -- a format change here is exactly the kind of thing
    schema_guard.py's per-record checks are meant to catch upstream;
    this function just refuses to fabricate a date."""
    if not raw:
        return None
    match = _DOTNET_DATE_RE.search(raw)
    if not match:
        return None
    try:
        from datetime import datetime, timezone
        millis = int(match.group(1))
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _parse_multiplier(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = _MULTIPLIER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_sports(payload: Any) -> Tuple[List[DkSport], List[SkipEntry], "schema_guard.SchemaCheckResult"]:
    check = schema_guard.check_sports(payload)
    if not check.ok:
        return [], [], check

    sports: List[DkSport] = []
    skipped: List[SkipEntry] = []
    for raw in payload.get("sports") or []:
        record_check = schema_guard.check_record("sports.sport", raw, schema_guard.EXPECTED_SPORT_KEYS)
        if not record_check.ok:
            skipped.append({"raw": raw, "reason": f"missing keys: {record_check.missing_keys}"})
            continue
        sports.append(DkSport(
            sport_id=raw["sportId"], code=raw["regionAbbreviatedSportName"], full_name=raw["fullName"],
            has_public_contests=bool(raw["hasPublicContests"]), is_enabled=bool(raw["isEnabled"]),
            sort_order=raw.get("sortOrder"), raw=raw,
        ))
    return sports, skipped, check


def normalize_game_types(payload: Any) -> Tuple[List[DkGameType], List[SkipEntry]]:
    game_types: List[DkGameType] = []
    skipped: List[SkipEntry] = []
    for raw in payload.get("GameTypes") or []:
        if "GameTypeId" not in raw or "SportId" not in raw or "Name" not in raw:
            skipped.append({"raw": raw, "reason": "missing GameTypeId/SportId/Name"})
            continue
        game_types.append(DkGameType(
            game_type_id=raw["GameTypeId"], sport_id=raw["SportId"], name=raw["Name"],
            description=raw.get("Description"), draft_type=raw.get("DraftType"),
            is_season_long=bool(raw.get("IsSeasonLong", False)), raw=raw,
        ))
    return game_types, skipped


def normalize_contests(payload: Any) -> Tuple[List[DkContest], List[SkipEntry], "schema_guard.SchemaCheckResult"]:
    check = schema_guard.check_contests(payload)
    if not check.ok:
        return [], [], check

    contests: List[DkContest] = []
    skipped: List[SkipEntry] = []
    for raw in payload.get("Contests") or []:
        record_check = schema_guard.check_record("contests.contest", raw, schema_guard.EXPECTED_CONTEST_KEYS)
        if not record_check.ok:
            skipped.append({"raw": raw, "reason": f"missing keys: {record_check.missing_keys}"})
            continue
        attr = raw.get("attr") or {}
        contests.append(DkContest(
            contest_id=raw["id"], name=raw["n"], sport_id=raw.get("s"), draft_group_id=raw.get("dg"),
            game_type=raw.get("gameType"), game_type_id=raw.get("gameTypeId"),
            start_time_raw=raw.get("sd"), start_time_iso=_parse_dotnet_date(raw.get("sd")),
            entry_fee=raw.get("fpp"), prize_pool=raw.get("po"), max_entries=raw.get("m"),
            current_entries=raw.get("a"), max_entries_per_user=raw.get("mec"),
            is_guaranteed=str(attr.get("IsGuaranteed", "")).lower() == "true",
            is_starred=str(attr.get("IsStarred", "")).lower() == "true",
            raw=raw,
        ))
    return contests, skipped, check


def normalize_draft_groups_to_slates(contests_payload: Any, contests: List[DkContest]) -> Tuple[List[DkSlate], List[SkipEntry]]:
    """DraftGroup is this milestone's canonical slate identifier (see
    module docstring). Deduplicates on DraftGroupId (the API's own
    DraftGroups list is already deduplicated relative to Contests --
    many contests share one DraftGroup) and attaches every contest_id
    that references it, satisfying "Slate has many Contests"."""
    slates: List[DkSlate] = []
    skipped: List[SkipEntry] = []
    contest_ids_by_dg: Dict[int, List[int]] = {}
    for c in contests:
        if c.draft_group_id is not None:
            contest_ids_by_dg.setdefault(c.draft_group_id, []).append(c.contest_id)

    sport_code = contests_payload.get("SelectedSport") or ""
    for raw in contests_payload.get("DraftGroups") or []:
        if "DraftGroupId" not in raw or "SportId" not in raw or "GameTypeId" not in raw:
            skipped.append({"raw": raw, "reason": "missing DraftGroupId/SportId/GameTypeId"})
            continue
        dg_id = raw["DraftGroupId"]
        slates.append(DkSlate(
            draft_group_id=dg_id, sport_id=raw["SportId"], sport_code=raw.get("Sport") or sport_code,
            game_type_id=raw["GameTypeId"], game_type_name=raw.get("GameType"),
            start_time=raw.get("StartDate"), tag=raw.get("DraftGroupTag") or None,
            label=raw.get("ContestStartTimeSuffix") or None, game_count=raw.get("GameCount"),
            contest_ids=contest_ids_by_dg.get(dg_id, []), raw=raw,
        ))
    return slates, skipped


def normalize_draftables(payload: Any, draft_group_id: int) -> Tuple[List[DkSlateGame], List[DkDraftable], List[SkipEntry], "schema_guard.SchemaCheckResult"]:
    check = schema_guard.check_draftables(payload)
    if not check.ok:
        return [], [], [], check

    games: List[DkSlateGame] = []
    skipped: List[SkipEntry] = []
    for raw in payload.get("competitions") or []:
        record_check = schema_guard.check_record("draftables.competition", raw, schema_guard.EXPECTED_COMPETITION_KEYS)
        if not record_check.ok:
            skipped.append({"raw": raw, "reason": f"missing keys: {record_check.missing_keys}"})
            continue
        home = raw.get("homeTeam") or {}
        away = raw.get("awayTeam") or {}
        games.append(DkSlateGame(
            competition_id=raw["competitionId"], sport_id=raw.get("sportId"), name=raw.get("name"),
            start_time=raw.get("startTime"),
            home_team=DkTeam(team_id=home["teamId"], abbreviation=home.get("abbreviation", ""), name=home.get("teamName"), city=home.get("city"), raw=home) if home.get("teamId") is not None else None,
            away_team=DkTeam(team_id=away["teamId"], abbreviation=away.get("abbreviation", ""), name=away.get("teamName"), city=away.get("city"), raw=away) if away.get("teamId") is not None else None,
            venue=raw.get("venue"), state=raw.get("competitionState"), raw=raw,
        ))

    draftables: List[DkDraftable] = []
    for raw in payload.get("draftables") or []:
        record_check = schema_guard.check_record("draftables.draftable", raw, schema_guard.EXPECTED_DRAFTABLE_KEYS)
        if not record_check.ok:
            skipped.append({"raw": raw, "reason": f"missing keys: {record_check.missing_keys}"})
            continue
        competition = raw.get("competition") or {}
        draftables.append(DkDraftable(
            draftable_id=raw["draftableId"], draft_group_id=draft_group_id, player_id=raw.get("playerId"),
            player_dk_id=raw.get("playerDkId"), display_name=raw["displayName"], first_name=raw.get("firstName"),
            last_name=raw.get("lastName"), position=raw.get("position"), roster_slot_id=raw.get("rosterSlotId"),
            salary=raw.get("salary"), status=raw.get("status"), team_id=raw.get("teamId"),
            team_abbreviation=raw.get("teamAbbreviation"), competition_id=competition.get("competitionId"),
            is_swappable=raw.get("isSwappable"), is_disabled=raw.get("isDisabled"), news_status=raw.get("newsStatus"),
            fppg=None,  # see module docstring -- never guessed from unlabeled draftStatAttributes
            raw=raw,
        ))
    return games, draftables, skipped, check


def normalize_game_type_rules(payload: Any, sport_id: Optional[int] = None) -> Tuple[Optional[DkRosterRules], "schema_guard.SchemaCheckResult"]:
    """`sport_id`: the /lineups/v1/gametypes/{id}/rules response does NOT
    include its own sportId (confirmed live -- absent from the payload
    entirely), so the caller must supply it from context (e.g. the
    DkGameType or DkSlate that led to this game_type_id). None when the
    caller doesn't have it -- never guessed."""
    check = schema_guard.check_game_type_rules(payload)
    if not check.ok:
        return None, check

    slots: List[DkRosterSlot] = []
    for entry in payload.get("lineupTemplate") or []:
        slot = entry.get("rosterSlot") or {}
        if "id" not in slot or "name" not in slot:
            continue
        slots.append(DkRosterSlot(
            roster_slot_id=slot["id"], name=slot["name"], description=slot.get("description"),
            order=entry.get("order"), scoring_multiplier=_parse_multiplier(slot.get("positionTipSubtext")), raw=entry,
        ))

    salary_cap = payload.get("salaryCap") or {}
    game_count = payload.get("gameCount") or {}
    team_count = payload.get("teamCount") or {}
    rules = DkRosterRules(
        game_type_id=payload["gameTypeId"], sport_id=sport_id, name=payload.get("gameTypeName") or "",
        draft_type=payload.get("draftType"), salary_cap_enabled=bool(salary_cap.get("isEnabled")),
        salary_cap=salary_cap.get("maxValue"), roster_slots=slots, unique_players=payload.get("uniquePlayers"),
        allow_late_swap=payload.get("allowLateSwap"), min_games=game_count.get("minValue"),
        min_teams=team_count.get("minValue"), rules_url=payload.get("rulesUrl"), raw=payload,
    )
    return rules, check
