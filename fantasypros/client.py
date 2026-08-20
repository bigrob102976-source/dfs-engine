"""FantasyPros Public API v2 client -- the ONLY module in this project
that talks to the FantasyPros network API. Mirrors
research/game_environment/providers/sportsgameodds.py's exact pattern
(urllib.request, x-api-key header, config.env_loader for the key).

Confirmed live (2026-08-19) via direct API calls -- NOT assumed from
documentation (FantasyPros' own docs page returned no machine-readable
content when checked):

    Base URL:  https://api.fantasypros.com/public/v2/json
    Endpoint:  GET /mlb/{season}/projections
    Params:    type=daily, date=YYYY-MM-DD, position=H|P
    Auth:      x-api-key request header

API KEY: read once, at request time, from the FANTASYPROS_API_KEY
environment variable -- never hardcoded, never logged, never returned in
any object this module produces (error messages never include it; no
function here ever echoes a header).

FREE-TIER LIMITATION (confirmed live, not documented anywhere
machine-readable): a "free" tier key is capped at a FIXED sample of 10
players per position, regardless of any query parameter (`limit`,
`page`, `offset`, `team_id` were all tried live and every one returned
the identical 10-player list). The response says so explicitly:
`"public_api_limited": true, "limit": 10, "tier": "free"`. This module
reads and preserves those fields rather than silently treating a
10-player response as "everything" -- see FantasyProsSnapshot's
public_api_limited/api_tier fields.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from config.env_loader import load_dashboard_env
from fantasypros.models import FantasyProsRawPlayer

# Milestone-standard module-import-time side effect (see
# research/game_environment/providers/sportsgameodds.py's identical
# comment): guarantees FANTASYPROS_API_KEY is in os.environ before this
# module ever reads it, for Python entry points Next.js doesn't spawn.
load_dashboard_env()

API_BASE_URL = "https://api.fantasypros.com/public/v2/json"
REQUEST_TIMEOUT_SECONDS = 15


class FantasyProsNotConfiguredError(Exception):
    """FANTASYPROS_API_KEY is not set. Expected/normal -- FantasyPros is
    an OPTIONAL provider; callers must treat this as "skip it", never a
    pipeline failure."""


class FantasyProsAuthenticationError(Exception):
    """The configured API key was rejected (HTTP 401/403)."""


class FantasyProsRateLimitedError(Exception):
    """HTTP 429 -- request/object quota reached."""


class FantasyProsUnavailableError(Exception):
    """Reachable but returned an unexpected error, or the response could
    not be parsed."""


def is_configured() -> bool:
    return bool(os.environ.get("FANTASYPROS_API_KEY"))


def _api_key() -> str:
    key = os.environ.get("FANTASYPROS_API_KEY")
    if not key:
        raise FantasyProsNotConfiguredError("FANTASYPROS_API_KEY is not set.")
    return key


def _get(path: str, params: Dict[str, str]) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_BASE_URL}{path}?{qs}"
    request = urllib.request.Request(
        url, headers={"x-api-key": _api_key(), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise FantasyProsAuthenticationError(f"FantasyPros rejected the configured API key (HTTP {exc.code}).") from exc
        if exc.code == 429:
            raise FantasyProsRateLimitedError("FantasyPros rate limit exceeded (HTTP 429).") from exc
        raise FantasyProsUnavailableError(f"FantasyPros returned HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FantasyProsUnavailableError(f"FantasyPros request failed: {exc}") from exc

    try:
        return json.loads(body)
    except ValueError as exc:
        raise FantasyProsUnavailableError("FantasyPros returned a malformed (non-JSON) response.") from exc


class DailyProjectionsResult:
    """One position's (H or P) daily-projections response, with the
    provider's own tier/limit metadata preserved -- see this module's
    docstring for why that must never be silently discarded."""

    def __init__(self, players: List[FantasyProsRawPlayer], count: int, public_api_limited: bool, tier: Optional[str]):
        self.players = players
        self.count = count  # FantasyPros' own reported total available (may exceed len(players) -- see public_api_limited)
        self.public_api_limited = public_api_limited
        self.tier = tier


def _parse_players(payload: dict, player_type: str) -> List[FantasyProsRawPlayer]:
    raw_list = payload.get("player") or []
    players: List[FantasyProsRawPlayer] = []
    for raw in raw_list:
        if not isinstance(raw, dict) or "name" not in raw:
            continue
        stats = {k: v for k, v in raw.items() if k not in ("fpid", "player_id", "yahooid", "team_id", "name")}
        players.append(
            FantasyProsRawPlayer(
                fpid=str(raw.get("fpid", raw.get("player_id", ""))),
                player_id=str(raw.get("player_id", raw.get("fpid", ""))),
                name=str(raw["name"]),
                team_id=str(raw.get("team_id") or ""),
                player_type=player_type,
                yahoo_id=str(raw["yahooid"]) if raw.get("yahooid") is not None else None,
                stats=stats,
            )
        )
    return players


def get_daily_projections(date: str, position: str, season: Optional[str] = None) -> DailyProjectionsResult:
    """position must be "H" (hitters) or "P" (pitchers) -- FantasyPros'
    own documented split for MLB daily projections; there is no
    "everyone" position value (confirmed: neither omitting `position` nor
    any other value was part of this milestone's live-verified request
    shape)."""
    if position not in ("H", "P"):
        raise ValueError(f"position must be 'H' or 'P', got {position!r}")
    season = season or date[:4]
    player_type = "hitter" if position == "H" else "pitcher"

    payload = _get(f"/mlb/{season}/projections", {"type": "daily", "date": date, "position": position})
    players = _parse_players(payload, player_type)
    return DailyProjectionsResult(
        players=players,
        count=int(payload.get("count") or len(players)),
        public_api_limited=bool(payload.get("public_api_limited", False)),
        tier=payload.get("tier"),
    )
