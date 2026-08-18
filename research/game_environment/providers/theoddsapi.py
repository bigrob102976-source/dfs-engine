"""The Odds API provider (Milestone 27) -- the SECONDARY/fallback odds
provider. SportsGameOdds (providers/sportsgameodds.py) remains PRIMARY;
this module only exists to fill in games SportsGameOdds didn't return a
usable market for. Normalization happens in this module
(normalize_theoddsapi_event below); everything downstream only ever
sees the same provider-agnostic NormalizedGameOdds SportsGameOdds
produces.

Official API reference (source of truth -- nothing here guesses
undocumented behavior):

    Base URL:   https://api.the-odds-api.com/v4
    Endpoint:   GET /sports/{sport}/odds
    Sport key:  baseball_mlb
    Markets:    h2h,spreads,totals (exactly what this module needs --
                never player props, never more regions/markets than
                required, since the free tier is credit-metered)
    Regions:    us (US sportsbooks only -- sufficient for MLB DK/FD-
                adjacent market consensus; requesting additional
                regions only burns quota for markets this project
                doesn't use)
    Odds format: american
    Auth:       apiKey QUERY STRING parameter (The Odds API does not
                document a header-based alternative, unlike
                SportsGameOdds) -- so the key CAN appear in the request
                URL. This module never logs, returns, or includes that
                URL (or the key) in any exception message/warning it
                raises; only a fixed, credential-free description of
                the failure is ever surfaced.
    Rate limit: reported via response headers x-requests-remaining /
                x-requests-used (documented) -- read in usage_status()
                below. A 401 means a bad/missing key; a 429 or a 401
                whose body indicates the plan/quota is exhausted both
                count as "plan restricted" for this project's coverage
                classification (see providers/coverage.py) -- but this
                module itself only ever raises the OddsProvider's
                already-defined exception types; the coverage
                classification distinction is made by the caller
                (vegas.py), not here.

API KEY: read once, at request time, from the THE_ODDS_API_KEY
environment variable -- never hardcoded, never logged. If unset,
is_configured() is False and get_odds() is never called (see
research/game_environment/collector.py's provider resolution).

CACHING: same discipline as sportsgameodds.py -- raw responses cached
under their own root (data/cache/theoddsapi/), separate from normalized
Game Environment snapshots, so a pipeline re-run within one process/day
never re-spends quota for the same (date) fetch.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional

from config.env_loader import load_dashboard_env
from research import cache
from research.game_environment.providers.base import (
    OddsProvider,
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.models import NormalizedGameOdds, ProviderUsageStatus
from research.game_environment.providers.normalizer import normalize_theoddsapi_event

load_dashboard_env()

API_BASE_URL = "https://api.the-odds-api.com/v4"
REQUEST_TIMEOUT_SECONDS = 15

_SPORT_KEY_BY_LEAGUE = {
    "MLB": "baseball_mlb",
}

_MARKETS = "h2h,spreads,totals"
_REGIONS = "us"
_ODDS_FORMAT = "american"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TheOddsAPIProvider(OddsProvider):
    """Real, credentialed SECONDARY odds provider. Only ever instantiated
    when THE_ODDS_API_KEY is set (see collector.py's provider
    resolution) -- is_configured() below is a defensive double-check,
    not the primary gate."""

    name = "theoddsapi"

    def __init__(self, api_key: Optional[str] = None, cache_root=None):
        self._api_key = api_key if api_key is not None else os.environ.get("THE_ODDS_API_KEY")
        self._cache_root = cache_root if cache_root is not None else cache.DEFAULT_CACHE_ROOT.parent / "theoddsapi"
        self._last_usage: Optional[ProviderUsageStatus] = None

    def provider_name(self) -> str:
        return "The Odds API"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _fetch(self, sport_key: str) -> List[dict]:
        # apiKey is a required query parameter per The Odds API's
        # documented auth scheme -- see module docstring for why this
        # module never echoes the URL in any error/log.
        url = (
            f"{API_BASE_URL}/sports/{sport_key}/odds/"
            f"?apiKey={self._api_key}&regions={_REGIONS}&markets={_MARKETS}&oddsFormat={_ODDS_FORMAT}"
        )
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
                self._record_usage_from_headers(dict(resp.headers))
        except urllib.error.HTTPError as exc:
            self._record_usage_from_headers(dict(exc.headers) if exc.headers else {})
            if exc.code in (401, 403):
                raise OddsProviderAuthenticationError("The Odds API rejected the configured API key.") from exc
            if exc.code == 429:
                raise OddsProviderRateLimitedError("The Odds API rate limit / quota exceeded (HTTP 429).") from exc
            raise OddsProviderUnavailableError(f"The Odds API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OddsProviderUnavailableError("The Odds API request failed (network error).") from exc

        try:
            data = json.loads(body)
        except ValueError as exc:
            raise OddsProviderUnavailableError("The Odds API returned a malformed (non-JSON) response.") from exc
        if not isinstance(data, list):
            raise OddsProviderUnavailableError("The Odds API returned an unexpected (non-list) response shape.")
        return data

    def _record_usage_from_headers(self, headers: dict) -> None:
        """Documented account-usage headers (case-insensitive) -- purely
        informational, never required for get_odds() to succeed."""
        lower_headers = {k.lower(): v for k, v in headers.items()}

        def _int_or_none(key: str) -> Optional[int]:
            value = lower_headers.get(key)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        used = _int_or_none("x-requests-used")
        remaining = _int_or_none("x-requests-remaining")
        limit = (used + remaining) if used is not None and remaining is not None else None
        self._last_usage = ProviderUsageStatus(
            provider=self.provider_name(),
            requests_used=used,
            requests_limit=limit,
            objects_used=None,
            objects_limit=None,
            retrieved_at=_now_iso(),
        )

    def get_odds(self, league: str, date: str) -> List[NormalizedGameOdds]:
        if not self.is_configured():
            raise OddsProviderNotConfiguredError("THE_ODDS_API_KEY is not set.")

        sport_key = _SPORT_KEY_BY_LEAGUE.get(league.upper())
        if sport_key is None:
            raise OddsProviderUnavailableError(f"League {league!r} is not supported by this provider integration.")

        # Cached by TODAY (the day of the actual API call), not the
        # requested slate `date` -- same reasoning as
        # sportsgameodds.py::_fetch_all_pages(): this endpoint isn't
        # itself date-filtered, so the cache is really "don't re-spend
        # quota within the same calendar day," independent of which
        # slate date is being resolved.
        cache_key = f"odds_{sport_key}"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def do_fetch() -> Optional[dict]:
            events = self._fetch(sport_key)
            return {"events": events, "fetched_at": _now_iso()}

        cached = cache.get_or_fetch(self._cache_root, today, cache_key, do_fetch)
        raw_events = (cached or {}).get("events", [])
        retrieved_at = _now_iso()

        results: List[NormalizedGameOdds] = []
        for raw_event in raw_events:
            normalized = normalize_theoddsapi_event(raw_event, retrieved_at)
            if normalized is not None:
                results.append(normalized)
        return results

    def usage_status(self) -> Optional[ProviderUsageStatus]:
        """Only populated after at least one real get_odds() call this
        process -- The Odds API reports usage via response headers on
        every request, not a separate endpoint, so there is nothing to
        report before the first call."""
        return self._last_usage
