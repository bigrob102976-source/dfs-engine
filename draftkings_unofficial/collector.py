"""Milestone 31.2 -- orchestrates client.py + normalizer.py + cache.py
+ persistence.py into the actual collection operations
scripts/audit_draftkings_unofficial.py and the dev provider use.

Every function here NEVER raises for an expected failure mode (a 404,
access-restricted, rate-limited, schema-changed, or unavailable
response) -- it returns a result object with a `status` field instead,
mirroring fantasypros/build.py's non-raising orchestration discipline.
Callers decide what "no active slate for this sport" or
"ACCESS_RESTRICTED" means for their own purposes (this milestone is
explicit that "no active slate" is not an error).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from draftkings_unofficial import client, identity, normalizer, persistence, schema_guard
from draftkings_unofficial.cache import DkUnofficialCache, get_default_cache
from draftkings_unofficial.models import DkContest, DkDraftable, DkGameType, DkRosterRules, DkSlate, DkSlateGame, DkSport, PlayerIdentityMatch

STATUS_OK = "ok"
STATUS_NO_ACTIVE_SLATE = "no_active_slate"
STATUS_ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
STATUS_SCHEMA_CHANGED = "SCHEMA_CHANGED"
STATUS_NOT_FOUND = "not_found"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class SportsResult:
    status: str
    sports: List[DkSport] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    schema_check: Optional[dict] = None


@dataclass
class SportUniverseResult:
    status: str
    sport_code: str
    contests: List[DkContest] = field(default_factory=list)
    slates: List[DkSlate] = field(default_factory=list)
    game_types: List[DkGameType] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    schema_check: Optional[dict] = None


@dataclass
class SlateDetailResult:
    status: str
    draft_group_id: int
    games: List[DkSlateGame] = field(default_factory=list)
    draftables: List[DkDraftable] = field(default_factory=list)
    roster_rules: Optional[DkRosterRules] = None
    identity_matches: List[PlayerIdentityMatch] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    schema_check: Optional[dict] = None
    rules_schema_check: Optional[dict] = None


def _handle_client_error(exc: Exception) -> str:
    from draftkings_unofficial.client import (
        DraftKingsUnofficialAccessRestrictedError,
        DraftKingsUnofficialNotFoundError,
        DraftKingsUnofficialRateLimitedError,
        DraftKingsUnofficialUnavailableError,
    )
    if isinstance(exc, DraftKingsUnofficialNotFoundError):
        return STATUS_NOT_FOUND
    if isinstance(exc, DraftKingsUnofficialAccessRestrictedError):
        return STATUS_ACCESS_RESTRICTED
    if isinstance(exc, DraftKingsUnofficialRateLimitedError):
        return STATUS_RATE_LIMITED
    if isinstance(exc, DraftKingsUnofficialUnavailableError):
        return STATUS_UNAVAILABLE
    raise exc


def collect_sports(save_snapshot: bool = True, cache: Optional[DkUnofficialCache] = None) -> SportsResult:
    cache = cache or get_default_cache()
    try:
        payload = cache.get_or_fetch("sports", "all", client.get_sports)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: translate any client error into a status
        return SportsResult(status=_handle_client_error(exc), error=str(exc))

    if save_snapshot:
        try:
            persistence.save_raw("sports", "sports", payload)
        except FileExistsError:
            pass

    sports, skipped, check = normalizer.normalize_sports(payload)
    if not check.ok:
        return SportsResult(status=STATUS_SCHEMA_CHANGED, schema_check=check.to_dict())
    return SportsResult(status=STATUS_OK, sports=sports, skipped=skipped, schema_check=check.to_dict())


def collect_sport_universe(sport_code: str, save_snapshot: bool = True, cache: Optional[DkUnofficialCache] = None) -> SportUniverseResult:
    cache = cache or get_default_cache()
    try:
        payload = cache.get_or_fetch("contests", sport_code, lambda: client.get_contests(sport_code))
    except Exception as exc:  # noqa: BLE001
        return SportUniverseResult(status=_handle_client_error(exc), sport_code=sport_code, error=str(exc))

    if save_snapshot:
        try:
            persistence.save_raw("contests", sport_code, payload)
        except FileExistsError:
            pass

    contests, contest_skipped, check = normalizer.normalize_contests(payload)
    if not check.ok:
        return SportUniverseResult(status=STATUS_SCHEMA_CHANGED, sport_code=sport_code, schema_check=check.to_dict())

    game_types, gt_skipped = normalizer.normalize_game_types(payload)
    slates, slate_skipped = normalizer.normalize_draft_groups_to_slates(payload, contests)

    if save_snapshot:
        try:
            persistence.save_raw("draftgroups", sport_code, payload.get("DraftGroups") or [])
        except FileExistsError:
            pass

    if not contests and not slates:
        return SportUniverseResult(
            status=STATUS_NO_ACTIVE_SLATE, sport_code=sport_code, contests=[], slates=[], game_types=game_types,
            skipped=contest_skipped + gt_skipped + slate_skipped, schema_check=check.to_dict(),
        )

    return SportUniverseResult(
        status=STATUS_OK, sport_code=sport_code, contests=contests, slates=slates, game_types=game_types,
        skipped=contest_skipped + gt_skipped + slate_skipped, schema_check=check.to_dict(),
    )


def collect_slate_detail(
    draft_group_id: int, sport_code: str, game_type_id: Optional[int] = None,
    research_package: Optional[dict] = None, save_snapshot: bool = True, cache: Optional[DkUnofficialCache] = None,
) -> SlateDetailResult:
    cache = cache or get_default_cache()
    try:
        payload = cache.get_or_fetch("draftables", str(draft_group_id), lambda: client.get_draftables(draft_group_id))
    except Exception as exc:  # noqa: BLE001
        return SlateDetailResult(status=_handle_client_error(exc), draft_group_id=draft_group_id, error=str(exc))

    if save_snapshot:
        try:
            persistence.save_raw("draftables", str(draft_group_id), payload)
        except FileExistsError:
            pass

    games, draftables, skipped, check = normalizer.normalize_draftables(payload, draft_group_id)
    if not check.ok:
        return SlateDetailResult(status=STATUS_SCHEMA_CHANGED, draft_group_id=draft_group_id, schema_check=check.to_dict())

    identity_matches = identity.match_draftables(draftables, sport_code, research_package)

    rules: Optional[DkRosterRules] = None
    rules_check_dict: Optional[dict] = None
    if game_type_id is not None:
        try:
            rules_payload = cache.get_or_fetch("rules", str(game_type_id), lambda: client.get_game_type_rules(game_type_id))
            if save_snapshot:
                try:
                    persistence.save_raw("rules", str(game_type_id), rules_payload)
                except FileExistsError:
                    pass
            sport_id = games[0].sport_id if games else None
            rules, rules_check = normalizer.normalize_game_type_rules(rules_payload, sport_id=sport_id)
            rules_check_dict = rules_check.to_dict()
        except Exception as exc:  # noqa: BLE001 -- rules are best-effort; a failure here shouldn't blank out the whole slate
            rules_check_dict = {"status": _handle_client_error(exc), "endpoint": "game_type_rules"}

    return SlateDetailResult(
        status=STATUS_OK, draft_group_id=draft_group_id, games=games, draftables=draftables, roster_rules=rules,
        identity_matches=identity_matches, skipped=skipped, schema_check=check.to_dict(), rules_schema_check=rules_check_dict,
    )
