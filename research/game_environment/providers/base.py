"""The one interface every ODDS provider must implement (Milestone 24).

Mirrors external_projections/base.py's ProjectionProvider contract
exactly (same NotConfigured/Unavailable/Authentication error split, same
"never return fabricated data" rule), plus one addition specific to a
metered API: OddsProviderRateLimitedError for a 429 response, so callers
can distinguish "the provider is down" from "we've hit our quota" and
report each accurately rather than lumping both into one generic failure.

All provider requests execute server-side only -- no provider code is
ever reachable from the browser, and no API key is ever passed to or
logged by client code (see providers/sportsgameodds.py's module
docstring for exactly how the key is read and never echoed).
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from research.game_environment.providers.models import NormalizedGameOdds, ProviderUsageStatus


class OddsProviderNotConfiguredError(RuntimeError):
    """No credentials are configured for this provider -- a normal,
    expected state (e.g. SPORTSGAMEODDS_API_KEY unset), not a failure.
    Distinct from OddsProviderUnavailableError: this means "we
    deliberately never tried", not "we tried and it didn't work"."""


class OddsProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring (network
    failure, timeout, malformed response, unexpected HTTP status other
    than 401/403/429)."""


class OddsProviderAuthenticationError(RuntimeError):
    """The provider was reachable but rejected the configured API key
    (HTTP 401/403)."""


class OddsProviderRateLimitedError(RuntimeError):
    """The provider returned HTTP 429 -- request/object quota exhausted.
    Callers should stop retrying for this run, not substitute mock data."""


class OddsProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for display (e.g. 'SportsGameOdds')."""
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """False whenever this provider cannot be used yet (e.g. missing
        API key). Never raises; callers check this BEFORE calling
        get_odds()."""
        raise NotImplementedError

    @abstractmethod
    def get_odds(self, league: str, date: str) -> List[NormalizedGameOdds]:
        """Every game's normalized odds for `league` (e.g. "MLB") on
        `date`. Raises OddsProviderNotConfiguredError /
        OddsProviderUnavailableError / OddsProviderAuthenticationError /
        OddsProviderRateLimitedError on failure -- never returns
        fabricated data, and never returns partial results silently
        mixed with fabricated ones."""
        raise NotImplementedError

    def usage_status(self) -> Optional[ProviderUsageStatus]:
        """Optional account usage/rate-limit info the provider itself
        can report. None if the provider offers no such endpoint or
        the call fails -- this is informational only, never required
        for get_odds() to work."""
        return None
