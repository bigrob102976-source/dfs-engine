"""The one interface every DFS salary provider must implement.

IMPORTANT DATA-SOURCE RULE (Milestone 13): a provider implementation
must NEVER scrape DraftKings HTML, automate a DraftKings login, or
depend on undocumented/private DraftKings endpoints. A provider is
either:

  1. A documented, credentialed third-party DFS-data API (none is
     configured in this environment -- see dfs/providers/config.py's
     module docstring for exactly what would be needed), or
  2. The clearly-labeled MockProvider (dfs/providers/mock_provider.py),
     used only to exercise the pipeline end-to-end when no real
     provider is configured. Its data is never presented as real
     DraftKings salaries -- see that module's docstring.

All provider requests execute server-side only (invoked from a Python
script run by the Node/Next.js orchestrator as a subprocess) -- no
provider code is ever reachable from the browser, and no API key is
ever passed to or logged by client code.
"""

from abc import ABC, abstractmethod

from dfs.providers.models import ProviderSlateResult


class ProviderUnavailableError(RuntimeError):
    """The provider is not configured/reachable at all (e.g. no API key,
    no network route). Distinct from an authentication failure -- this
    means "we never got to try", not "we tried and were rejected"."""


class ProviderAuthenticationError(RuntimeError):
    """The provider was reachable but rejected the configured credentials."""


class ProviderNoSlateError(RuntimeError):
    """The provider is configured and reachable but has no slate for the
    requested date/sport/site (e.g. an off day)."""


class DFSSalaryProvider(ABC):
    """One standard interface. Implementations normalize whatever their
    upstream API returns into ProviderPlayer/ProviderSlateResult -- the
    rest of the application (dfs/pool_builder.py, the optimizer) only
    ever sees that normalized shape."""

    name: str = "unnamed_provider"
    requires_api_key: bool = False

    @abstractmethod
    def get_slate(self, date: str, sport: str = "MLB", site: str = "draftkings") -> ProviderSlateResult:
        """Returns every slate (and each slate's players) the provider
        has for `date`. Raises ProviderUnavailableError /
        ProviderAuthenticationError / ProviderNoSlateError on failure --
        never returns fabricated data, never silently returns an empty
        result to mean "failed" (an empty `slates` list legitimately
        means "no slates today")."""
        raise NotImplementedError
