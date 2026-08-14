"""The one interface every EXTERNAL PROJECTION provider must implement.

IMPORTANT DATA-SOURCE RULE (Milestone 17): a provider implementation
must NEVER scrape a third-party DFS site's HTML, automate a login, or
depend on undocumented/private endpoints. A provider is either:

  1. A documented, credentialed third-party projections API (none is
     configured in this environment -- see
     external_projections/bluecollar_provider.py's module docstring for
     exactly what is still needed before that provider can go live), or
  2. The clearly-labeled MockExternalProvider
     (external_projections/mock_provider.py), used only to exercise the
     baseline/adjustment/comparison pipeline end-to-end when no real
     provider is configured. Its data is never presented as real
     BlueCollar (or any other real provider's) projections.

All provider requests execute server-side only, exactly like
dfs/providers/ -- no provider code is ever reachable from the browser,
and no API key is ever passed to or logged by client code.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo


class ProjectionProviderNotConfiguredError(RuntimeError):
    """The provider has no credentials/documentation yet -- a normal,
    expected state (e.g. BlueCollar today), not a failure. Distinct from
    ProjectionProviderUnavailableError: this means "we deliberately never
    tried", not "we tried and it didn't work"."""


class ProjectionProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring (network
    failure, unexpected response shape, etc.)."""


class ProjectionProviderAuthenticationError(RuntimeError):
    """The provider was reachable but rejected the configured credentials."""


class ProjectionProvider(ABC):
    """One standard interface. Implementations normalize whatever their
    upstream API returns into ExternalProjectionPlayer/ExternalSlateInfo
    -- the rest of the application (the adjustment engine, the merge
    step, the dashboard) only ever sees that normalized shape."""

    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for display (e.g. 'BlueCollar DFS')."""
        raise NotImplementedError

    def provider_version(self) -> Optional[str]:
        """Optional provider-reported data/API version. None if the
        provider doesn't expose one."""
        return None

    @abstractmethod
    def is_configured(self) -> bool:
        """False whenever this provider cannot be used yet -- missing
        credentials, missing documentation, or (for BlueCollar today)
        deliberately not implemented. Never raises; callers check this
        BEFORE calling list_slates/get_projections."""
        raise NotImplementedError

    @abstractmethod
    def list_slates(self, date: str, sport: str = "MLB", site: str = "draftkings") -> List[ExternalSlateInfo]:
        """Every slate the provider has for `date`. Raises
        ProjectionProviderNotConfiguredError / ProjectionProviderUnavailableError
        / ProjectionProviderAuthenticationError on failure -- never
        returns fabricated data."""
        raise NotImplementedError

    @abstractmethod
    def get_projections(self, slate_id: str) -> List[ExternalProjectionPlayer]:
        """Every player projection the provider has for `slate_id`.
        Same failure-mode contract as list_slates."""
        raise NotImplementedError
