"""Milestone 31.0 -- an ISOLATED, audit-only client for the
FantasyData/SportsDataIO MLB API. This module exists ONLY to test API
access and inspect response shape/quality; it is NOT a production
projection provider and is not wired into any existing pipeline
(Native, AI, FantasyPros, Vegas, Ownership, Optimizer). See
scripts/audit_fantasydata_historical.py, the only caller.

Mirrors the project's existing external-API pattern (urllib.request,
config.env_loader for the key, fantasypros/client.py's error-handling
shape) rather than inventing a new one.

Auth: Ocp-Apim-Subscription-Key request header (SportsDataIO's own
documented auth scheme -- distinct from FantasyPros' x-api-key).

API KEY: read once, at request time, from the FANTASYDATA_API_KEY
environment variable -- never hardcoded, never logged, never returned
in any object this module produces, never placed in a URL/query
string. Error messages never include it.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from config.env_loader import load_dashboard_env

# Milestone-standard module-import-time side effect (see
# fantasypros/client.py's identical comment): guarantees
# FANTASYDATA_API_KEY is in os.environ before this module ever reads
# it, for Python entry points Next.js doesn't spawn.
load_dashboard_env()

API_BASE_URL = "https://api.sportsdata.io/v3/mlb"
REQUEST_TIMEOUT_SECONDS = 20


class FantasyDataNotConfiguredError(Exception):
    """FANTASYDATA_API_KEY is not set."""


class FantasyDataAuthenticationError(Exception):
    """The configured API key was rejected (HTTP 401/403)."""


class FantasyDataRateLimitedError(Exception):
    """HTTP 429 -- request/object quota reached."""


class FantasyDataUnavailableError(Exception):
    """Reachable but returned an unexpected error, or the response
    could not be parsed."""


def is_configured() -> bool:
    return bool(os.environ.get("FANTASYDATA_API_KEY"))


def _api_key() -> str:
    key = os.environ.get("FANTASYDATA_API_KEY")
    if not key:
        raise FantasyDataNotConfiguredError("FANTASYDATA_API_KEY is not set.")
    return key


def _get(path: str) -> Any:
    """GETs one absolute-path endpoint under API_BASE_URL. The API key
    is sent ONLY via the Ocp-Apim-Subscription-Key header -- never as a
    query parameter -- per this milestone's explicit instruction."""
    url = f"{API_BASE_URL}{path}"
    request = urllib.request.Request(
        url, headers={"Ocp-Apim-Subscription-Key": _api_key(), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise FantasyDataAuthenticationError(f"FantasyData rejected the configured API key (HTTP {exc.code}).") from exc
        if exc.code == 429:
            raise FantasyDataRateLimitedError("FantasyData rate limit exceeded (HTTP 429).") from exc
        raise FantasyDataUnavailableError(f"FantasyData returned HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FantasyDataUnavailableError(f"FantasyData request failed: {exc}") from exc

    try:
        parsed = json.loads(body) if body else None
    except ValueError as exc:
        raise FantasyDataUnavailableError("FantasyData returned a malformed (non-JSON) response.") from exc

    return {"status": status, "data": parsed}


def get_player_game_projection_stats_by_date(date_str: str) -> Dict[str, Any]:
    """TEST 1 -- historical per-player-per-game projections.
    GET /projections/json/PlayerGameProjectionStatsByDate/{date_str}"""
    return _get(f"/projections/json/PlayerGameProjectionStatsByDate/{date_str}")


def get_fantasy_game_stats_by_date(date_str: str) -> Dict[str, Any]:
    """TEST 2 -- historical actual per-player-per-game results.
    GET /stats/json/FantasyGameStatsByDate/{date_str}"""
    return _get(f"/stats/json/FantasyGameStatsByDate/{date_str}")


def get_dfs_slates_by_date(date_str: str) -> Dict[str, Any]:
    """TEST 3 -- historical DFS slate metadata (DraftKings/FanDuel/etc).
    GET /projections/json/DfsSlatesByDate/{date_str}"""
    return _get(f"/projections/json/DfsSlatesByDate/{date_str}")
