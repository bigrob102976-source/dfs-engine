"""Raw HTTP client for DraftKings' unofficial public JSON endpoints --
the ONLY module in this project that talks to them. Every endpoint
below was confirmed LIVE during Milestone 31.2's discovery pass (not
assumed from the 2021 unofficial documentation, which this milestone
found to be a reasonable but imperfect starting point -- see
draftkings_unofficial/README.md's "Known Limitations").

CONFIRMED LIVE ENDPOINTS (2026-08-20):

    Sports:           GET https://api.draftkings.com/sites/US-DK/sports/v1/sports?format=json
    Contest discovery: GET https://www.draftkings.com/lobby/getcontests?sport={SPORT_CODE}
    Draftables:        GET https://api.draftkings.com/draftgroups/v1/draftgroups/{DRAFT_GROUP_ID}/draftables
    Game type rules:   GET https://api.draftkings.com/lineups/v1/gametypes/{GAME_TYPE_ID}/rules
    Contest details:   GET https://api.draftkings.com/contests/v1/contests/{CONTEST_ID}?format=json

All five require no authentication (no login, no cookies, no API key)
and returned real, current data with a plain User-Agent header. None
of the 400/401/403/404/429/5xx paths below were speculative -- 404 was
observed directly (invalid draftGroupId) and returns
`{"errorStatus": {"code": ..., "developerMessage": ...}}`; the others
are handled defensively per this milestone's explicit error-handling
requirement even though they weren't all triggered live (triggering
429 deliberately would violate "do not make unnecessary calls").

This is UNOFFICIAL, UNDOCUMENTED DraftKings data -- the schema can
change at any time without notice. See schema_guard.py for how a
shape change is detected and reported instead of crashing.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

USER_AGENT = "Mozilla/5.0 (compatible; BigMoneyDFS-dev/1.0)"
REQUEST_TIMEOUT_SECONDS = 20

SPORTS_URL = "https://api.draftkings.com/sites/US-DK/sports/v1/sports?format=json"
CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport={sport_code}"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{draft_group_id}/draftables"
GAME_TYPE_RULES_URL = "https://api.draftkings.com/lineups/v1/gametypes/{game_type_id}/rules"
CONTEST_DETAILS_URL = "https://api.draftkings.com/contests/v1/contests/{contest_id}?format=json"


class DraftKingsUnofficialError(Exception):
    """Base class for every error this client can raise."""


class DraftKingsUnofficialNotFoundError(DraftKingsUnofficialError):
    """HTTP 404 -- the requested resource (draft group, contest, game
    type) doesn't exist, e.g. an expired/invalid ID."""


class DraftKingsUnofficialAccessRestrictedError(DraftKingsUnofficialError):
    """HTTP 401/403, or a response that looks like a login/CAPTCHA page
    rather than JSON -- per this milestone's explicit "do not build
    bypass mechanisms" boundary, this is reported and the caller moves
    on to other resources; it is never retried with credentials."""


class DraftKingsUnofficialRateLimitedError(DraftKingsUnofficialError):
    """HTTP 429."""


class DraftKingsUnofficialUnavailableError(DraftKingsUnofficialError):
    """Reachable but returned an unexpected 4xx/5xx, a malformed/empty
    body, or the request failed at the network level (timeout, DNS,
    connection refused)."""


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DraftKingsUnofficialNotFoundError(f"DraftKings resource not found (HTTP 404): {url}") from exc
        if exc.code in (401, 403):
            raise DraftKingsUnofficialAccessRestrictedError(f"DraftKings restricted access (HTTP {exc.code}): {url}") from exc
        if exc.code == 429:
            raise DraftKingsUnofficialRateLimitedError(f"DraftKings rate limit exceeded (HTTP 429): {url}") from exc
        raise DraftKingsUnofficialUnavailableError(f"DraftKings returned HTTP {exc.code}: {exc.reason} ({url})") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        # Covers DNS failures, connection refused, and request timeouts --
        # urllib wraps DNS/connection errors in URLError.
        raise DraftKingsUnofficialUnavailableError(f"DraftKings request failed: {exc} ({url})") from exc

    if not body.strip():
        raise DraftKingsUnofficialUnavailableError(f"DraftKings returned an empty response body ({url})")

    stripped = body.lstrip()
    if stripped.startswith("<"):
        # An HTML page (login wall, CAPTCHA, generic error page) instead
        # of JSON -- treated as access-restricted, not a schema change
        # (the endpoint isn't returning its normal contract at all).
        raise DraftKingsUnofficialAccessRestrictedError(f"DraftKings returned HTML instead of JSON (likely a login/CAPTCHA wall): {url}")

    try:
        return json.loads(body)
    except ValueError as exc:
        raise DraftKingsUnofficialUnavailableError(f"DraftKings returned invalid JSON ({url}): {exc}") from exc


def get_sports() -> Dict[str, Any]:
    return _get_json(SPORTS_URL)


def get_contests(sport_code: str) -> Dict[str, Any]:
    return _get_json(CONTESTS_URL.format(sport_code=sport_code))


def get_draftables(draft_group_id: int) -> Dict[str, Any]:
    return _get_json(DRAFTABLES_URL.format(draft_group_id=draft_group_id))


def get_game_type_rules(game_type_id: int) -> Dict[str, Any]:
    return _get_json(GAME_TYPE_RULES_URL.format(game_type_id=game_type_id))


def get_contest_details(contest_id: int) -> Optional[Dict[str, Any]]:
    return _get_json(CONTEST_DETAILS_URL.format(contest_id=contest_id))
