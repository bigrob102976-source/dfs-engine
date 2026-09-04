"""NFL M7 -- resolves and fetches real NFL Vegas odds events, honestly
reporting NOT_CONFIGURED rather than falling back to mock (mirrors
research/game_environment/collector.py::get_configured_vegas_provider()'s
exact "never silently mock for Vegas" posture -- a wrong Vegas number is
worse than a missing one).

Reuses the real, tested SportsGameOddsProvider/TheOddsAPIProvider HTTP
client classes (auth, retry/error classification, pagination, caching)
by calling their existing raw-fetch methods directly, then applies
nfl/odds_provider_normalizer.py's NFL-specific team resolution -- see
that module's docstring for exactly why NFL cannot go through either
provider's public get_odds() method (which hardwires MLB's team
crosswalk internally) without risking silent team-code corruption.

Resolution priority (mirrors collector.py::get_configured_vegas_provider,
scoped to NFL, no per-game consensus/fallback -- nfl/odds_matching.py
already takes the first available book per matched game, so a full
multi-provider consensus layer is out of this milestone's scope):

  1. SPORTSGAMEODDS_API_KEY set -> SportsGameOdds is the source. If
     THE_ODDS_API_KEY is ALSO set, source is "multi_provider_configured"
     (informational only -- The Odds API is only actually queried if
     SportsGameOdds returns zero usable events); else
     "sportsgameodds_configured".
  2. Only THE_ODDS_API_KEY set -> The Odds API alone, source
     "theoddsapi_only_configured".
  3. Neither set -> source "not_configured", zero events, never mock.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from research import cache
from research.game_environment.providers.base import (
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.models import NormalizedGameOdds
from research.game_environment.providers.sportsgameodds import SportsGameOddsProvider
from research.game_environment.providers.theoddsapi import TheOddsAPIProvider

from nfl.odds_provider_normalizer import normalize_sportsgameodds_event_nfl, normalize_theoddsapi_event_nfl

NFL_LEAGUE_ID_SPORTSGAMEODDS = "NFL"  # confirmed via SportsGameOdds' public docs (sportsgameodds.com/docs/data-types/leagues)
NFL_SPORT_KEY_THEODDSAPI = "americanfootball_nfl"  # confirmed via The Odds API's public docs (the-odds-api.com/liveapi/guides/v4/)

NOT_CONFIGURED = "not_configured"
SPORTSGAMEODDS_CONFIGURED = "sportsgameodds_configured"
THEODDSAPI_ONLY_CONFIGURED = "theoddsapi_only_configured"
MULTI_PROVIDER_CONFIGURED = "multi_provider_configured"

_PROVIDER_ERRORS = (
    OddsProviderNotConfiguredError,
    OddsProviderUnavailableError,
    OddsProviderAuthenticationError,
    OddsProviderRateLimitedError,
)

_THEODDSAPI_NFL_CACHE_ROOT = cache.DEFAULT_CACHE_ROOT.parent / "theoddsapi_nfl"


@dataclass
class NflOddsFetchResult:
    events: List[NormalizedGameOdds] = field(default_factory=list)
    source_provenance: str = NOT_CONFIGURED
    provider_errors: List[str] = field(default_factory=list)


def get_nfl_odds_source_provenance() -> str:
    import os

    sgo_key = os.environ.get("SPORTSGAMEODDS_API_KEY")
    odds_api_key = os.environ.get("THE_ODDS_API_KEY")
    if sgo_key:
        return MULTI_PROVIDER_CONFIGURED if odds_api_key else SPORTSGAMEODDS_CONFIGURED
    if odds_api_key:
        return THEODDSAPI_ONLY_CONFIGURED
    return NOT_CONFIGURED


def _fetch_sportsgameodds_nfl_events() -> List[NormalizedGameOdds]:
    provider = SportsGameOddsProvider()
    if not provider.is_configured():
        raise OddsProviderNotConfiguredError("SPORTSGAMEODDS_API_KEY is not set.")
    # Bypasses get_odds() deliberately -- see this module's docstring
    # and nfl/odds_provider_normalizer.py's for why. _fetch_all_pages()
    # is the real, tested raw-fetch/auth/pagination/caching method;
    # nothing about the HTTP layer is duplicated here.
    raw_events = provider._fetch_all_pages(NFL_LEAGUE_ID_SPORTSGAMEODDS)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    results: List[NormalizedGameOdds] = []
    for raw_event in raw_events:
        normalized = normalize_sportsgameodds_event_nfl(raw_event, retrieved_at)
        if normalized is not None:
            results.append(normalized)
    return results


def _fetch_theoddsapi_nfl_events() -> List[NormalizedGameOdds]:
    provider = TheOddsAPIProvider()
    if not provider.is_configured():
        raise OddsProviderNotConfiguredError("THE_ODDS_API_KEY is not set.")

    # Reimplements get_odds()'s caching wrapper at the NFL layer (own
    # cache root/key, so NFL never shares or collides with MLB's
    # data/cache/theoddsapi/ namespace) around the provider's real,
    # tested _fetch() HTTP call -- see this module's docstring for why
    # get_odds() itself can't be called directly for NFL.
    cache_key = f"odds_{NFL_SPORT_KEY_THEODDSAPI}"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def do_fetch():
        events = provider._fetch(NFL_SPORT_KEY_THEODDSAPI)
        return {"events": events, "fetched_at": datetime.now(timezone.utc).isoformat()}

    cached = cache.get_or_fetch(_THEODDSAPI_NFL_CACHE_ROOT, today, cache_key, do_fetch)
    raw_events = (cached or {}).get("events", [])
    retrieved_at = datetime.now(timezone.utc).isoformat()

    results: List[NormalizedGameOdds] = []
    for raw_event in raw_events:
        normalized = normalize_theoddsapi_event_nfl(raw_event, retrieved_at)
        if normalized is not None:
            results.append(normalized)
    return results


def fetch_nfl_odds_events() -> NflOddsFetchResult:
    """Never fabricates: returns an empty event list with source
    "not_configured" when neither provider has a real key set (checked
    at call time, not import time, so tests can set/unset env vars
    freely)."""
    provenance = get_nfl_odds_source_provenance()
    if provenance == NOT_CONFIGURED:
        return NflOddsFetchResult(events=[], source_provenance=NOT_CONFIGURED, provider_errors=[])

    events: List[NormalizedGameOdds] = []
    errors: List[str] = []

    if provenance in (SPORTSGAMEODDS_CONFIGURED, MULTI_PROVIDER_CONFIGURED):
        try:
            events.extend(_fetch_sportsgameodds_nfl_events())
        except _PROVIDER_ERRORS as exc:
            errors.append(f"SportsGameOdds: {exc}")

    if provenance in (THEODDSAPI_ONLY_CONFIGURED, MULTI_PROVIDER_CONFIGURED) and not events:
        try:
            events.extend(_fetch_theoddsapi_nfl_events())
        except _PROVIDER_ERRORS as exc:
            errors.append(f"The Odds API: {exc}")

    return NflOddsFetchResult(events=events, source_provenance=provenance, provider_errors=errors)
