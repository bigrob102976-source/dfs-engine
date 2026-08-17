"""SportsGameOdds provider (Milestone 24) -- the ONLY module in this
project that talks to the SportsGameOdds network API. Normalization
(providers/normalizer.py), consensus math (providers/consensus.py), and
everything downstream only ever see NormalizedGameOdds -- never this
module's raw JSON.

Official API reference (per this milestone's explicit instructions --
treated as the source of truth; nothing here guesses undocumented
behavior):

    Base URL:     https://api.sportsgameodds.com/v2
    Endpoint:     GET /events
    MLB filter:   leagueID=MLB
    Odds filter:  oddsAvailable=true
    Auth:         x-api-key request header (preferred over the
                  provider's also-supported ?apiKey= query string, so a
                  credential never appears in a URL/log line)

API KEY: read once, at request time, from the SPORTSGAMEODDS_API_KEY
environment variable -- never hardcoded, never logged, never returned in
any object this module produces (is_configured()/provider_name() never
echo it; error messages never include it).

PAGINATION: SportsGameOdds' v2 list endpoints are cursor-paginated. This
module follows whatever cursor field the response actually contains
(checked defensively under a few plausible key names -- see
_next_cursor()) until no more pages are returned, rather than assuming a
single page always has everything.

CACHING: raw responses are cached via research.cache.get_or_fetch under
their OWN root (data/cache/sportsgameodds/), kept separate from the
normalized Game Environment snapshots persisted in
game_environment_snapshots/ -- a cache hit never repeats a network call
for the same (date) within one process, but never masks a genuine
provider outage on the NEXT run (no TTL/eviction needed -- see
research/cache.py's own module docstring for why that's sufficient here).
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from research import cache
from research.game_environment.providers.base import (
    OddsProvider,
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.models import NormalizedGameOdds, ProviderUsageStatus
from research.game_environment.providers.normalizer import normalize_sportsgameodds_event

API_BASE_URL = "https://api.sportsgameodds.com/v2"
REQUEST_TIMEOUT_SECONDS = 15
MAX_PAGES = 10  # hard ceiling so a misbehaving cursor can never loop forever / burn quota unbounded

DEFAULT_CACHE_ROOT = cache.DEFAULT_CACHE_ROOT.parent / "sportsgameodds"

_LEAGUE_TO_PROVIDER_LEAGUE_ID = {
    "MLB": "MLB",
    # Multi-sport-ready (per this milestone's explicit "do not hardcode
    # solely to MLB" instruction): only MLB is actually normalized in
    # this milestone (providers/normalizer.py only implements MLB event
    # parsing), but the provider layer itself imposes no MLB-only
    # restriction on the leagueID it will pass through.
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_cursor(payload: dict) -> Optional[str]:
    """Checked under a few plausible key names since this module must
    not assume one specific undocumented shape -- if SportsGameOdds
    returns no more pages, every one of these is naturally absent/None
    and pagination simply stops after one page."""
    for key in ("nextCursor", "next_cursor", "cursor"):
        value = payload.get(key)
        if value:
            return value
    return None


class SportsGameOddsProvider(OddsProvider):
    """Real, credentialed odds provider. is_mock is inherited as False
    (OddsProvider's default) -- this class is only ever instantiated
    when SPORTSGAMEODDS_API_KEY is actually set (see vegas.py's provider
    resolution), so is_configured() below is really just a defensive
    double-check, not the primary gate."""

    name = "sportsgameodds"

    def __init__(self, api_key: Optional[str] = None, cache_root=DEFAULT_CACHE_ROOT):
        self._api_key = api_key if api_key is not None else os.environ.get("SPORTSGAMEODDS_API_KEY")
        self._cache_root = cache_root

    def provider_name(self) -> str:
        return "SportsGameOdds"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _fetch_page(self, league_id: str, cursor: Optional[str]) -> dict:
        params = f"leagueID={league_id}&oddsAvailable=true"
        if cursor:
            params += f"&cursor={cursor}"
        url = f"{API_BASE_URL}/events?{params}"
        request = urllib.request.Request(url, headers={"x-api-key": self._api_key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise OddsProviderAuthenticationError(
                    f"SportsGameOdds rejected the configured API key (HTTP {exc.code})."
                ) from exc
            if exc.code == 429:
                raise OddsProviderRateLimitedError(
                    "SportsGameOdds rate limit exceeded (HTTP 429) -- request/object quota reached."
                ) from exc
            raise OddsProviderUnavailableError(f"SportsGameOdds returned HTTP {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OddsProviderUnavailableError(f"SportsGameOdds request failed: {exc}") from exc

        try:
            return json.loads(body)
        except ValueError as exc:
            raise OddsProviderUnavailableError("SportsGameOdds returned a malformed (non-JSON) response.") from exc

    def _fetch_all_pages(self, league_id: str) -> List[dict]:
        """Follows pagination (see _next_cursor) up to MAX_PAGES. Cached
        as one combined payload per (date, league) so a pipeline re-run
        within the same process/day never re-fetches the same events."""

        def do_fetch() -> Optional[dict]:
            events: List[dict] = []
            cursor: Optional[str] = None
            for _ in range(MAX_PAGES):
                page = self._fetch_page(league_id, cursor)
                page_events = page.get("data")
                if isinstance(page_events, list):
                    events.extend(page_events)
                cursor = _next_cursor(page)
                if not cursor:
                    break
            return {"events": events, "fetched_at": _now_iso()}

        # cache.get_or_fetch never caches a None result, so a failed
        # fetch (do_fetch raising) still propagates -- caching only ever
        # happens on genuine success.
        cache_key = f"events_{league_id.lower()}"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cached = cache.get_or_fetch(self._cache_root, today, cache_key, do_fetch)
        return (cached or {}).get("events", [])

    def get_odds(self, league: str, date: str) -> List[NormalizedGameOdds]:
        if not self.is_configured():
            raise OddsProviderNotConfiguredError("SPORTSGAMEODDS_API_KEY is not set.")

        league_id = _LEAGUE_TO_PROVIDER_LEAGUE_ID.get(league.upper())
        if league_id is None:
            raise OddsProviderUnavailableError(f"League {league!r} is not supported by this provider integration.")

        raw_events = self._fetch_all_pages(league_id)
        retrieved_at = _now_iso()

        results: List[NormalizedGameOdds] = []
        for raw_event in raw_events:
            normalized = normalize_sportsgameodds_event(raw_event, retrieved_at)
            if normalized is not None:
                results.append(normalized)
        return results

    def usage_status(self) -> Optional[ProviderUsageStatus]:
        """SportsGameOdds does not document a dedicated account-usage
        endpoint in this milestone's source-of-truth instructions --
        rather than guess an undocumented one, this returns None (no
        usage data available) until an official endpoint is confirmed.
        Never a reason get_odds() itself would fail."""
        return None
