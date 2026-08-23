"""BlueCollar DFS projection provider -- MLB DraftKings endpoint.

Official, documented API (source of truth -- nothing here guesses an
endpoint, header, or field; see https://bluecollardfs.com/developers):

    Base URL:    https://bluecollardfs.com
    Endpoint:    GET /api/mlb_draftkings
    Auth:        Authorization: ApiKey <BLUECOLLAR_API_KEY>  (header)
    Rate limit:  200 requests/day across all endpoints (documented) --
                 see CACHING below.

Documented response shape:

    {"slates": [{"slate": str, "slate_type": str, "date": str,
                 "updated": str, "info": [{"name": str, "team": str,
                 "position": str, "opponent": str, "projection": ...,
                 "salary": ..., "value": ...}, ...]}, ...]}

No player or slate identifier is documented. `external_player_id` and
`slate_id` below are therefore LOCALLY DERIVED (a slug of name+team+
position, and a slug of date+index+slate name respectively) -- a stable
local key, never fabricated projection/identity data. `projection`/
`salary`/`value` are documented only as present, not with an exact JSON
type -- parsed defensively (numeric or numeric-string both accepted);
a value that fails to parse is left None rather than guessed.

API KEY: read once, at request time, from the BLUECOLLAR_API_KEY
environment variable -- never hardcoded, never logged, never included
in any exception message, error, log line, snapshot, or test fixture.

CACHING: research/cache.py's generic get_or_fetch, keyed by date -- one
real network call per date, no matter how many times a page or script
asks for it that day (the documented 200 requests/day limit is shared
across every BlueCollar endpoint, so this module must not re-fetch on
every page load). BlueCollar's own "updated" timestamp is carried
through onto every normalized slate/player record so callers can judge
freshness themselves; this module never re-fetches just because
"updated" looks old -- that is a caller/admin-refresh decision, not
something this provider does on its own.

This provider is registered as "bluecollar" in
external_projections/registry.py; EXTERNAL_PROJECTION_PROVIDER=bluecollar
selects it, but is_configured() (see below) is the real gate -- it
requires BLUECOLLAR_API_KEY to actually be set, not just this env var.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from config.env_loader import load_dashboard_env
from dfs.team_abbreviations import normalize_dk_team_abbr
from external_projections.base import (
    ProjectionProvider,
    ProjectionProviderAuthenticationError,
    ProjectionProviderNotConfiguredError,
    ProjectionProviderUnavailableError,
)
from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
from research import cache

load_dashboard_env()

API_BASE_URL = "https://bluecollardfs.com"
API_ENDPOINT = "/api/mlb_draftkings"
REQUEST_TIMEOUT_SECONDS = 15

_CACHE_ROOT = cache.DEFAULT_CACHE_ROOT.parent / "bluecollar"
_SLATE_ID_PREFIX = "bluecollar"


def _slugify(value: Optional[str]) -> str:
    if not value:
        return "slate"
    return "-".join(str(value).strip().lower().split()) or "slate"


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    f = _coerce_float(value)
    return int(f) if f is not None else None


def _bluecollar_date(iso_date: str) -> str:
    """Converts a "YYYY-MM-DD" date into BlueCollar's own date format --
    confirmed via a real, live, authenticated response (2026-08-23):
    each slate's "date" field is "MM_DD_YY" (e.g. "08_23_26"), not ISO.
    This is observed fact, not a guess -- the documentation's example
    payload only showed "..." placeholders with no real format."""
    year, month, day = iso_date.split("-")
    return f"{month}_{day}_{year[2:]}"


def _player_key(name: str, team: str, position: str) -> str:
    """Locally-derived, stable identifier -- BlueCollar's documented
    response includes no player ID of its own."""
    return f"{_slugify(name)}|{normalize_dk_team_abbr(team).lower()}|{_slugify(position)}"


class BlueCollarProvider(ProjectionProvider):
    """Real, credentialed BlueCollar DFS provider. Only ever usable when
    BLUECOLLAR_API_KEY is set -- is_configured() below is the real gate,
    checked by every caller before list_slates()/get_projections()."""

    name = "bluecollar"
    is_mock = False

    def __init__(self, api_key: Optional[str] = None, cache_root: Optional[Path] = None):
        self._api_key = api_key if api_key is not None else os.environ.get("BLUECOLLAR_API_KEY")
        self._cache_root = cache_root if cache_root is not None else _CACHE_ROOT

    def provider_name(self) -> str:
        return "BlueCollar DFS"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _fetch_raw(self) -> dict:
        # Guarded again here (not just by is_configured()) so a direct
        # _fetch_raw()/_fetch() call can never silently proceed with no
        # key -- this is the one place the Authorization header is built,
        # and the key is never captured in a variable that outlives this
        # method or appears in any exception message below.
        if not self._api_key:
            raise ProjectionProviderNotConfiguredError(
                "BLUECOLLAR_API_KEY is not set -- BlueCollar DFS is not connected."
            )
        url = f"{API_BASE_URL}{API_ENDPOINT}"
        request = urllib.request.Request(
            url, headers={"Authorization": f"ApiKey {self._api_key}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ProjectionProviderAuthenticationError(
                    "BlueCollar DFS rejected the configured API key (HTTP 401 -- missing/invalid key)."
                ) from exc
            if exc.code == 403:
                raise ProjectionProviderAuthenticationError(
                    "BlueCollar DFS: the configured API key does not have access to this endpoint (HTTP 403)."
                ) from exc
            if exc.code == 429:
                raise ProjectionProviderUnavailableError(
                    "BlueCollar DFS: daily request limit reached (HTTP 429)."
                ) from exc
            raise ProjectionProviderUnavailableError(f"BlueCollar DFS returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProjectionProviderUnavailableError("BlueCollar DFS request failed (network error).") from exc

        try:
            data = json.loads(body)
        except ValueError as exc:
            raise ProjectionProviderUnavailableError("BlueCollar DFS returned a malformed (non-JSON) response.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("slates"), list):
            raise ProjectionProviderUnavailableError("BlueCollar DFS response is missing the expected 'slates' list.")
        return data

    def _fetch(self) -> dict:
        # Milestone: BlueCollar's slates aren't keyed by a single request
        # date the way most providers are -- the endpoint returns
        # whatever slates it currently has, each carrying its OWN "date"
        # field. Cached once per calendar day this method is called
        # (research/cache.py's own date-bucketed convention), which is
        # what keeps repeated page loads within the documented 200/day
        # budget without this provider needing to invent per-slate-date
        # cache keys for data it hasn't fetched yet.
        today = datetime.now(timezone.utc).date().isoformat()
        result = cache.get_or_fetch(self._cache_root, today, "mlb_draftkings", self._fetch_raw)
        if result is None:
            raise ProjectionProviderUnavailableError("BlueCollar DFS fetch returned no data.")
        return result

    def _raw_slates_for(self, date: str) -> List[dict]:
        doc = self._fetch()
        target = _bluecollar_date(date)
        return [s for s in doc.get("slates", []) if isinstance(s, dict) and s.get("date") == target]

    def list_slates(self, date: str, sport: str = "MLB", site: str = "draftkings") -> List[ExternalSlateInfo]:
        if sport.upper() != "MLB":
            # This provider only ever calls the /api/mlb_draftkings
            # endpoint -- every slate it returns is inherently MLB/DK.
            return []
        slates = self._raw_slates_for(date)
        out: List[ExternalSlateInfo] = []
        for i, raw in enumerate(slates):
            slate_id = f"{_SLATE_ID_PREFIX}-{date}-{i}-{_slugify(raw.get('slate'))}"
            info = raw.get("info") if isinstance(raw.get("info"), list) else []
            out.append(ExternalSlateInfo(
                slate_id=slate_id,
                slate_name=raw.get("slate") if isinstance(raw.get("slate"), str) else None,
                sport="MLB",
                site=site,
                player_count=len(info),
            ))
        return out

    def get_projections(self, slate_id: str) -> List[ExternalProjectionPlayer]:
        # slate_id shape: "bluecollar-YYYY-MM-DD-<index>-<slug>" -- the
        # date itself contains hyphens, so this can't be parsed with a
        # simple maxsplit; split unbounded and reassemble the fixed-width
        # YYYY/MM/DD pieces explicitly instead.
        parts = slate_id.split("-")
        if len(parts) < 5 or parts[0] != _SLATE_ID_PREFIX:
            raise ProjectionProviderUnavailableError(f"Not a recognized BlueCollar slate_id: {slate_id!r}.")
        date = "-".join(parts[1:4])
        try:
            index = int(parts[4])
        except ValueError:
            raise ProjectionProviderUnavailableError(f"Not a recognized BlueCollar slate_id: {slate_id!r}.")

        slates = self._raw_slates_for(date)
        if index >= len(slates):
            raise ProjectionProviderUnavailableError(f"BlueCollar slate {slate_id!r} no longer exists.")
        raw = slates[index]
        slate_name = raw.get("slate") if isinstance(raw.get("slate"), str) else None
        updated_at = raw.get("updated") if isinstance(raw.get("updated"), str) else ""
        info = raw.get("info") if isinstance(raw.get("info"), list) else []

        players: List[ExternalProjectionPlayer] = []
        for p in info:
            if not isinstance(p, dict):
                continue
            name = p.get("name")
            team = p.get("team")
            position = p.get("position")
            if not name or not team or not position:
                continue  # never fabricate an identity field BlueCollar didn't supply
            projection = _coerce_float(p.get("projection"))
            if projection is None:
                # ExternalProjectionPlayer.projection is non-optional --
                # a record with no genuinely parseable projection is
                # dropped rather than defaulted to a fabricated 0.0
                # (which would read as a real "projected for zero
                # points" rather than "unknown").
                continue
            players.append(ExternalProjectionPlayer(
                external_player_id=_player_key(name, team, position),
                name=name,
                team=normalize_dk_team_abbr(team),
                position=position,
                projection=projection,
                provider_name=self.provider_name(),
                updated_at=updated_at,
                slate_id=slate_id,
                opponent=p.get("opponent") if isinstance(p.get("opponent"), str) else None,
                salary=_coerce_int(p.get("salary")),
                slate_name=slate_name,
            ))
        return players
